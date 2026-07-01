# ⚡ face_recognition-ng

> **Riconosci volti. Traccia identità. Tutto in real-time.**

---

## 🤔 Cos'è e a cosa serve?

Hai mai voluto sapere **chi è la persona davanti alla tua telecamera** — in tempo reale, senza toccare nulla?

O magari hai una foto di qualcuno e vuoi scoprire se quella faccia appare da qualche parte sul web, su Instagram, su siti russi, su TinEye... automaticamente?

**face_recognition-ng** fa esattamente questo. È un sistema completo di:

- 🎥 **Riconoscimento facciale live** — punta la webcam (o una IP cam), e il sistema identifica le persone in meno di 100ms
- 🔍 **OSINT automatizzato** — carica una foto, inserisci un nome, e lui cerca su Google Lens, Yandex, TinEye, 3000+ siti social, costruisce un grafo delle connessioni e genera un PDF professionale
- 🧠 **Ragionamento trasparente** — puoi vedere *step by step* cosa sta facendo, quali fonti ha trovato, quanto è "a rischio" il profilo
- 📊 **Dashboard moderna** — split-view: camera a sinistra, intelligence a destra, con tab Evidenze, Grafo, Stats e Progress bar animata

---

## 🆕 Novità v4.7.0 — InsightFace + Supervision

> **Upgrade del motore CV: da dlib a InsightFace ArcFace + Supervision**

### Cosa è cambiato

| Componente | Prima (v4.6.x) | Ora (v4.7.0) |
|---|---|---|
| **Face detector** | dlib HOG | InsightFace `buffalo_l` (ArcFace) |
| **Embedding size** | 128D | 512D |
| **Accuracy (LFW)** | ~99.3% | ~99.7% |
| **Velocità (CPU)** | baseline | 3-5x più veloce |
| **GPU support** | ❌ | ✅ (`VISION_CTX_ID=0`) |
| **Tracking** | ❌ | ✅ ByteTrack (Supervision) |
| **Frame annotato** | ❌ | ✅ bbox + label overlay |
| **`track_id` in WS** | ❌ | ✅ ID stabile per ogni volto |

### Nuovo modulo `vision_engine.py`

Tutta la logica CV è ora centralizzata in `VisionEngine`:

```python
from vision_engine import VisionEngine

engine = VisionEngine(ctx_id=-1)  # -1=CPU, 0=GPU

# Detection + embedding in un colpo
detections, embeddings = engine.process_frame(frame, track=True)

# Annotazione frame con bbox + label
annotated = engine.annotate_frame(frame, detections, labels)

# Trigger zone OSINT (lancia OSINT solo dentro un'area)
engine.set_trigger_zone(polygon=[(100,100),(500,100),(500,400),(100,400)], frame_resolution=(1280,720))
if engine.faces_in_zone(detections):
    # avvia pipeline OSINT
    ...
```

### Compatibilità

- ✅ **Tutti gli endpoint REST rimangono invariati** — nessuna breaking change
- ✅ **`face_db.py` e `known_faces.db` compatibili** — i volti già registrati continuano a funzionare
- ✅ **Fallback automatico a dlib** se InsightFace non è installato
- ✅ **`/compare`** aggiornato con distanza coseno (compatibile sia con embeddings 128D che 512D)
- ✅ **`/health`** ora indica il backend attivo: `{"backend": "insightface"}` o `{"backend": "dlib"}`

### Migrazione

```bash
# Aggiorna dipendenze (aggiunge insightface, supervision, onnxruntime)
pip install -r requirements.txt

# Il modello buffalo_l viene scaricato automaticamente al primo avvio (~300MB)
FR_API_TOKEN=secret python api_server.py
```

> **Nota GPU**: per usare la GPU imposta `VISION_CTX_ID=0`. Richiede CUDA + `onnxruntime-gpu` al posto di `onnxruntime`.

---

## 🎯 Casi d'uso

| Chi | Come lo usa |
|-----|-------------|
| 🔐 Security researcher | Verificare se un volto appare in data breach o leak pubblici |
| 🕵️ OSINT analyst | Raccogliere evidenze su un target da più fonti in un click |
| 🏢 Aziende / accesso fisico | Riconoscimento su IP cam all'ingresso, log automatico |
| 👨‍💻 Developer | API REST + WebSocket pronta da integrare in qualsiasi app |
| 🎓 Studenti / ricercatori | Studiare pipeline ML + OSINT su un progetto reale |

---

## ✨ Perché è utile (davvero)

- **Zero API key da pagare** — tutto gira in locale o su endpoint pubblici gratuiti
- **Veloce** — InsightFace `buffalo_l` fa encoding in ~30ms su CPU, ~5ms su GPU
- **Modulare** — ogni componente (OSINT, face DB, rate limiter, PDF) è indipendente
- **Privacy-first** — nessun dato esce se non vuoi tu (puoi mettere `OSINT_ENABLE_EXTERNAL=false`)
- **Tutto in una pagina** — apri `localhost:8000/dashboard/index.html` e hai tutto: cam, OSINT, grafo, stats, PDF

---

## 🚀 Avvio in 30 secondi

```bash
pip install -r requirements.txt
FR_API_TOKEN=changeme python api_server.py
```

Apri il browser su:
- **`http://localhost:8000/dashboard/index.html`** — Dashboard completa
- **`http://localhost:8000/docs`** — Swagger UI (testa ogni endpoint)

---

## 🖥️ Come funziona la dashboard

```
┌─────────────────────┬─────────────────────────────────────────┐
│  📷 Camera live     │  🔍 OSINT Intelligence                  │
│                     │                                         │
│  ┌───────────────┐  │  [Target: Mario Rossi] [📷 Foto] [▶ Vai]│
│  │  video feed   │  │  ━━━━━━━━━━━━━━━━━━━━━━━ 73%           │
│  │  + box volti  │  │  ● Hashing ✓  ● RevImg ✓  ● Social...  │
│  └───────────────┘  │                                         │
│  Mario Rossi 94%    │  🧠 Ragion. │ 📋 Evid. │ 🕸 Grafo │ 📊 │
│  [track_id: 3]      │  ✓ 3 profili trovati su Instagram...    │
└─────────────────────┴─────────────────────────────────────────┘
[LOG] 00:01 Match: Mario Rossi (94%) | 00:02 OSINT completato
```

---

---
---

# 🔧 Documentazione Tecnica

---

## Endpoint HTTP

| Metodo | Path | Descrizione | Rate limit |
|--------|------|-------------|------------|
| GET | `/health` | Health check + backend info | nessuno |
| POST | `/encode` | Encoding volto da immagine | — |
| POST | `/detect` | Rilevamento volti | — |
| POST | `/compare` | Confronto encoding (coseno) | — |
| POST | `/register` | Registra volto noto nel DB | — |
| GET | `/known` | Lista volti noti | — |
| DELETE | `/known/{id}` | Elimina volto noto | — |
| POST | `/osint/image` | Reverse image search (cache TTL 24h) | 3/60s |
| POST | `/osint/social` | Ricerca social per nome/username | 10/60s |
| POST | `/osint/full` | Pipeline OSINT completa + risk_score | 2/60s |
| POST | `/report/pdf` | PDF OSINT scaricabile | 2/60s |
| GET | `/osint/stats` | Stats aggregate + ultime run | 20/60s |
| GET | `/osint/graph/{id}` | Grafo nodi/archi per una run | 20/60s |
| WS | `/ws/stream` | Stream webcam real-time + tracking | — |
| WS | `/ws/rtsp` | Stream RTSP real-time + tracking | — |

Tutti gli endpoint (tranne `/health`) richiedono `Authorization: Bearer <token>`.

---

## Variabili ENV

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `FR_API_TOKEN` | `changeme` | Token di autenticazione |
| `FR_DB_PATH` | `faces.db` | Path database SQLite volti |
| `FR_OSINT_DB_PATH` | `osint_results.db` | Path database SQLite OSINT |
| `VISION_CTX_ID` | `-1` | InsightFace ctx_id: `-1`=CPU, `0`=GPU |
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

Il rate limiter (`rate_limiter.py`) è **in-memory, zero dipendenze esterne** (stdlib Python: `threading`, `time`).

- Algoritmo: **fixed-window** per IP (con supporto `X-Forwarded-For` per proxy/nginx)
- Risposta 429 include: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`
- Cleanup automatico ogni `RATE_LIMIT_CLEANUP_SECS` secondi
- Per deploy distribuito: sostituire `_store` in `RateLimiter` con Redis
- Per disabilitare: `RATE_LIMIT_ENABLED=false`

---

## OSINT — Cache, DB e Grafo

### Cache TTL
Ogni chiamata a `/osint/image` e `/osint/full` calcola un `image_hash` (MD5 12 char).
Se esiste una run recente (entro `OSINT_CACHE_TTL_HOURS`), la risposta viene servita dal DB senza ripetere le ricerche esterne. La risposta include `from_cache: true`.

### Database OSINT (`osint_db.py`)
SQLite con:
- `osint_runs`: `image_hash`, `target_name`, `run_type`, `risk_score`, `created_at`, `raw_json`
- `osint_evidence`: `source`, `url`, `kind`, `confidence`, `meta_json` per ogni run
- 7 indici per performance

### Grafo OSINT (`GET /osint/graph/{run_id}`)
Formato compatibile con Neo4j, vis.js, Maltego:
```json
{
  "nodes": [
    {"id": "person:Mario Rossi", "type": "person"},
    {"id": "site:google_lens",   "type": "site"},
    {"id": "account:https://instagram.com/...", "type": "account"}
  ],
  "edges": [
    {"source": "person:Mario Rossi", "target": "site:google_lens", "label": "reverse_image"}
  ],
  "node_count": 3,
  "edge_count": 2
}
```

### Risk Score
Calcolato su `/osint/full` e `/report/pdf`:
- Social found **40%** + Maigret hits **40%** + Reverse image results **20%**
- Valore `0.0–1.0`, salvato in DB per ogni run

---

## Test

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

Verifica: tutti gli endpoint, cache hit/miss, rate limit 429, PDF magic bytes, grafo nodi/archi.

---

## Docker

```bash
# CPU
docker build -t face-recognition-ng .
docker run -p 8000:8000 -e FR_API_TOKEN=secret face-recognition-ng

# GPU
docker build -f Dockerfile.gpu -t face-recognition-ng-gpu .
docker run -p 8000:8000 --gpus all -e FR_API_TOKEN=secret -e VISION_CTX_ID=0 face-recognition-ng-gpu
```

---

## Struttura file

```
api_server.py          — Server FastAPI v4.7.0, tutti gli endpoint
vision_engine.py       — Engine CV: InsightFace + Supervision (detection, tracking, zone)
rate_limiter.py        — Rate limiter in-memory (stdlib, zero deps)
osint_db.py            — Database SQLite OSINT (run, evidenze, grafo)
osint_engine.py        — Reverse image search engine
social_lookup.py       — Ricerca profili social
maigret_wrapper.py     — Wrapper Maigret (3000+ siti)
report_generator.py    — Generatore PDF ReportLab
face_db.py             — Database SQLite volti noti
websocket_stream.py    — Stream webcam/RTSP v2.0 (tracking + frame annotato)
smoke_test.py          — Test end-to-end server live
tests/                 — Pytest unit + integration
dashboard/index.html   — Dashboard split-view (camera + OSINT)
```
