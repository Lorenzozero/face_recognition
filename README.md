# face_recognition-ng

Server REST + WebSocket per riconoscimento facciale e OSINT, basato su [InsightFace](https://github.com/deepinsight/insightface) e FastAPI.

---

## Avvio rapido

```bash
pip install -r requirements_ng.txt
FR_API_TOKEN=changeme python api_server.py
# Swagger UI: http://localhost:8000/docs
```

---

## Endpoint HTTP

| Metodo | Path | Descrizione | Rate limit |
|--------|------|-------------|------------|
| GET | `/health` | Health check | nessuno |
| POST | `/encode` | Encoding volto da immagine | — |
| POST | `/detect` | Rilevamento volti | — |
| POST | `/compare` | Confronto encoding | — |
| POST | `/register` | Registra volto noto nel DB | — |
| GET | `/known` | Lista volti noti | — |
| DELETE | `/known/{id}` | Elimina volto noto | — |
| POST | `/osint/image` | Reverse image search (cache TTL 24h) | 3/60s |
| POST | `/osint/social` | Ricerca social per nome/username | 10/60s |
| POST | `/osint/full` | Pipeline OSINT completa + risk_score | 2/60s |
| POST | `/report/pdf` | PDF OSINT scaricabile | 2/60s |
| GET | `/osint/stats` | Stats aggregate + ultime run | 20/60s |
| GET | `/osint/graph/{id}` | Grafo nodi/archi per una run (Neo4j/vis.js) | 20/60s |
| WS | `/ws/stream` | Stream webcam real-time | — |
| WS | `/ws/rtsp` | Stream RTSP real-time | — |

Tutti gli endpoint (tranne `/health`) richiedono header `Authorization: Bearer <token>`.

---

## Variabili ENV

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `FR_API_TOKEN` | `changeme` | Token di autenticazione |
| `FR_DB_PATH` | `faces.db` | Path database SQLite volti |
| `FR_OSINT_DB_PATH` | `osint_results.db` | Path database SQLite OSINT |
| `OSINT_CACHE_TTL_HOURS` | `24` | Ore validità cache OSINT |
| `OSINT_ENABLE_EXTERNAL` | `true` | Abilita chiamate HTTP esterne nell'engine OSINT |
| `OSINT_ENABLE_MAIGRET` | `true` | Abilita ricerca Maigret |
| `OSINT_TIMEOUT` | `30` | Timeout httpx per OSINT (secondi) |
| `OSINT_MAX_SITES` | `500` | Max siti Maigret per ricerca |
| `RATE_LIMIT_ENABLED` | `true` | Abilita rate limiting (`false` per dev/test) |
| `RATE_LIMIT_WINDOW_SECS` | `60` | Durata finestra rate limit (secondi) |
| `RATE_LIMIT_OSINT_IMAGE` | `3` | Max req `/osint/image` per finestra |
| `RATE_LIMIT_OSINT_FULL` | `2` | Max req `/osint/full` e `/report/pdf` |
| `RATE_LIMIT_OSINT_SOCIAL` | `10` | Max req `/osint/social` |
| `RATE_LIMIT_OSINT_STATS` | `20` | Max req `/osint/stats` e `/osint/graph` |
| `RATE_LIMIT_CLEANUP_SECS` | `300` | Intervallo cleanup rate limiter in memoria |

---

## Rate Limiting

Il rate limiter (`rate_limiter.py`) è **in-memory, zero dipendenze esterne** (usa solo stdlib Python: `threading`, `time`).

- Algoritmo: **fixed-window** per IP (con supporto `X-Forwarded-For` per proxy/nginx).
- Risposta 429 include header `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`.
- Cleanup automatico ogni `RATE_LIMIT_CLEANUP_SECS` secondi (background task asyncio all'avvio).
- Per deploy distribuito: sostituire `_store` in `RateLimiter` con un backend Redis.
- Per disabilitare in dev/test: `RATE_LIMIT_ENABLED=false`.

---

## OSINT — Cache, DB e Grafo

### Cache TTL
Ogni chiamata a `/osint/image` e `/osint/full` calcola un `image_hash` (MD5 12 char) dell'immagine.
Se esiste una run recente (entro `OSINT_CACHE_TTL_HOURS`) per quell'hash, la risposta viene servita dal DB senza ripetere le ricerche esterne. La risposta include `from_cache: true`.

### Database OSINT (`osint_db.py`)
Salva ogni run OSINT in SQLite con:
- `osint_runs`: `image_hash`, `target_name`, `run_type`, `risk_score`, `created_at`, `raw_json`
- `osint_evidence`: per ogni run, lista di evidenze con `source`, `url`, `kind`, `confidence`, `meta_json`
- 7 indici per performance su `image_hash`, `run_type`, `created_at`, `risk_score`, `run_id`, `source`, `kind`

### Grafo OSINT (`GET /osint/graph/{run_id}`)
Restituisce nodi e archi per una run in formato JSON compatibile con **Neo4j**, **vis.js**, **Maltego**:
```json
{
  "nodes": [
    {"id": "person:Mario Rossi", "type": "person", ...},
    {"id": "site:google_lens",   "type": "site", ...},
    {"id": "account:https://instagram.com/mariorossi", "type": "account", ...}
  ],
  "edges": [
    {"source": "person:Mario Rossi", "target": "site:google_lens", "label": "reverse_image"},
    {"source": "site:google_lens", "target": "account:...", "label": "profile"}
  ],
  "node_count": 3,
  "edge_count": 2
}
```

### Risk Score
Calcolato automaticamente su `/osint/full` e `/report/pdf`:
- Social found (40%) + Maigret hits (40%) + Reverse image results (20%)
- Valore `0.0–1.0`, salvato in DB per ogni run

---

## Test e Smoke Test

### Unit test (mock, nessun modello reale)
```bash
pip install -r requirements_test.txt
FR_API_TOKEN=test-token-ci RATE_LIMIT_ENABLED=false pytest tests/ -v -k "not integration"
```

### Integration test (InsightFace reale)
```bash
pip install -r requirements_ng.txt
FR_API_TOKEN=test-token-ci RATE_LIMIT_ENABLED=false pytest tests/test_integration_real.py -v
```

### Smoke test end-to-end (server live)
```bash
# Terminale 1
FR_API_TOKEN=changeme python api_server.py

# Terminale 2
python smoke_test.py
```

Il smoke test verifica:
- `/health`, `/encode`, `/detect`, `/compare`, `/register`, `/known`
- `/osint/image` (cache miss + cache hit)
- `/osint/social`, `/osint/full` (risk_score)
- `/osint/stats` (tutti i campi aggregati)
- `/osint/graph/{run_id}` (nodi/archi) + 404 su run inesistente
- `/report/pdf` (magic bytes `%PDF`, dimensione > 10KB)
- Rate limit 429 su `/osint/social`

Salva automaticamente il PDF in `smoke_test_report.pdf`.

---

## Docker

```bash
docker build -t face-recognition-ng .
docker run -p 8000:8000 -e FR_API_TOKEN=secret face-recognition-ng
# oppure con GPU:
docker build -f Dockerfile.gpu -t face-recognition-ng-gpu .
```

---

## Struttura file principali

```
api_server.py          — Server FastAPI v4.5, tutti gli endpoint
rate_limiter.py        — Rate limiter in-memory (stdlib, zero deps extra)
osint_db.py            — Database SQLite OSINT (run, evidenze, grafo)
osint_engine.py        — Reverse image search engine
social_lookup.py       — Ricerca profili social
maigret_wrapper.py     — Wrapper Maigret (3000+ siti)
report_generator.py    — Generatore PDF con ReportLab
face_db.py             — Database SQLite volti noti
websocket_stream.py    — Stream webcam/RTSP
smoke_test.py          — Test end-to-end server live
tests/                 — Pytest unit + integration tests
```
