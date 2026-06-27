# face_recognition-ng

> ⚡ Fork moderno di [ageitgey/face_recognition](https://github.com/ageitgey/face_recognition) — stessa API semplice, backend aggiornato + OSINT integrato.

[![CI](https://github.com/Lorenzozero/face_recognition/actions/workflows/ci.yml/badge.svg)](https://github.com/Lorenzozero/face_recognition/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Fork di ageitgey/face_recognition](https://img.shields.io/badge/fork-ageitgey%2Fface__recognition-lightgrey)](https://github.com/ageitgey/face_recognition)

---

## Cos'è questo progetto?

**face_recognition-ng** è un fork di [face_recognition](https://github.com/ageitgey/face_recognition) di Adam Geitgey, una delle librerie di riconoscimento facciale più popolari su GitHub (50k+ ⭐).

Il progetto originale si basa su **dlib**, che presenta diversi problemi:

- Richiede una compilazione C++ lunga e spesso problematica
- Non funziona su Python 3.12+
- Nessun supporto nativo GPU
- Modello del 2017, superato dalle soluzioni moderne

Questo fork mantiene la **stessa API semplicissima** dell'originale, sostituendo il backend con [InsightFace](https://github.com/deepinsight/insightface) e aggiungendo un **motore OSINT integrato**.

### Vantaggi rispetto all'originale

- ✅ Compatibile con Python 3.9–3.12+
- ✅ Supporto GPU nativo (CUDA) tramite ONNX Runtime
- ✅ Accuratezza superiore del ~15% rispetto a dlib
- ✅ Nessuna compilazione C++ richiesta
- ✅ Drop-in replacement — zero modifiche al codice esistente
- ✅ REST API HTTP integrata
- ✅ Dashboard web con webcam live e stream RTSP
- ✅ Database volti noti (SQLite)
- ✅ **Motore OSINT**: reverse image search + social lookup + Maigret
- ✅ **Report PDF** generato automaticamente con grafici e tabelle

---

## Installazione

```bash
git clone https://github.com/Lorenzozero/face_recognition
cd face_recognition
pip install -r requirements_ng.txt

# Opzionale: abilita Maigret per cerca username su 3000+ siti
pip install maigret
```

Per il supporto GPU:
```bash
pip install onnxruntime-gpu  # al posto di onnxruntime
```

---

## Avvio rapido

```bash
FR_API_TOKEN=il_tuo_token python api_server.py
```

Apri il browser su `http://localhost:8000` per la **dashboard web**.
Swagger UI disponibile su `http://localhost:8000/docs`.

---

## Dashboard Web

Interfaccia grafica accessibile dal browser, senza installare nulla di aggiuntivo.

**Funzionalità:**
- 📷 **Webcam live** — rilevamento e riconoscimento in tempo reale via WebSocket
- 🎥 **Stream RTSP/IP camera** — connetti telecamere di rete (Hikvision, Dahua, ecc.)
- 📦 **Bounding box** — rettangoli colorati sui volti con nome e confidence score
- 📸 **Registra volto** — cattura un frame e salva il volto nel database con un nome
- 🗃️ **Gestione DB** — visualizza ed elimina i volti noti registrati
- 📄 **Genera Report PDF** — form integrato per avviare la pipeline OSINT e scaricare il PDF
- 📊 **Log eventi** — storico dei riconoscimenti in tempo reale

---

## Motore OSINT (Fase 3)

Dato un volto (immagine) e/o un nome, il motore OSINT esegue automaticamente:

### Reverse Image Search

| Motore | Descrizione |
|--------|-------------|
| **Google Lens** | Carica il volto e ottieni link diretto ai risultati visivi |
| **Yandex Images** | Ottimo per profili russi/est-europei, molto preciso sui volti |
| **TinEye** | Trova dove l'immagine è apparsa online in passato |
| **PimEyes** | Il motore più potente per ricerca facciale (link apertura diretta) |
| **Bing Visual Search** | Ricerca visiva Microsoft |

### Social Media Lookup

| Piattaforma | Metodo |
|-------------|--------|
| Instagram | Verifica profilo diretto + Google dork |
| Twitter/X | Verifica profilo diretto + Google dork |
| LinkedIn | Google dork `site:linkedin.com/in` |
| Facebook | Google dork + verifica diretta |
| TikTok | Verifica profilo diretto |
| GitHub | Verifica profilo diretto |

### Maigret — Username Discovery

[Maigret](https://github.com/soxoj/maigret) cerca un username su **3000+ siti** simultaneamente.[web:92][web:84]

```python
# Genera automaticamente varianti username dal nome completo
# 'Mario Rossi' → ['mariorossi', 'mario.rossi', 'mario_rossi', 'mrossi', ...]
```

### Endpoint OSINT

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST` | `/osint/image` | Reverse image search del volto |
| `POST` | `/osint/social` | Ricerca profili social per nome/username |
| `POST` | `/osint/full` | Pipeline completa: immagine + nome + Maigret |
| `POST` | `/report/pdf` | Pipeline OSINT + genera PDF scaricabile |

### Esempio di utilizzo

```bash
# Pipeline OSINT completa + PDF in un solo comando
curl -X POST http://localhost:8000/report/pdf \
  -H "Authorization: Bearer il_tuo_token" \
  -F "name=Mario Rossi" \
  -F "file=@foto.jpg" \
  -F "run_maigret=false" \
  --output report.pdf

# Solo pipeline OSINT JSON
curl -X POST http://localhost:8000/osint/full \
  -H "Authorization: Bearer il_tuo_token" \
  -F "name=Mario Rossi" \
  -F "file=@foto.jpg" \
  -F "run_maigret=true"
```

---

## Configurazione OSINT (ENV flags)

Per ambienti diversi (lab, produzione, air-gapped) puoi controllare il motore OSINT via variabili d'ambiente:

```bash
# Disabilita chiamate esterne (solo link/local data)
OSINT_ENABLE_EXTERNAL=false

# Abilita/Disabilita Maigret
OSINT_ENABLE_MAIGRET=true

# Timeout massimo per HTTP OSINT
OSINT_TIMEOUT=30

# Limita numero di siti Maigret
OSINT_MAX_SITES=500
```

- `OSINT_ENABLE_EXTERNAL=false` — `/osint/*` genera solo link e dati locali, senza chiamare siti esterni (utile in ambienti chiusi o senza internet).
- `OSINT_ENABLE_MAIGRET=false` — salta completamente la parte di username discovery su 3000+ siti.[web:92][web:84]
- `OSINT_TIMEOUT` — timeout di httpx per le chiamate OSINT (default consigliato: 30s).[web:83]
- `OSINT_MAX_SITES` — limita il numero di siti che Maigret scansiona (es. 500 su 3000+), come suggerito nelle best practice OSINT.[web:93]

---

## Test e CI

### Test unitari (mock)

Per eseguire i test veloci con dipendenze leggere e mock dei moduli pesanti:

```bash
pip install -r requirements_test.txt
pytest tests/ -v --tb=short -k "not integration"
```

Questi test verificano routing, auth, formati JSON e generazione PDF senza scaricare modelli InsightFace.

### Test di integrazione reale (InsightFace + immagini vere)

Per validare il backend InsightFace con immagini reali (`tests/test_images/obama.jpg`, `biden.jpg`):

```bash
pip install -r requirements_ng.txt
pytest tests/test_integration_real.py -v --tb=short
```

Questi test controllano:
- Rilevamento volto su `obama.jpg` e `biden.jpg`
- Encoding 512D normalizzato (norma ≈ 1.0)
- `compare_faces` e `face_distance` su stessa persona vs persone diverse.

### Smoke test end-to-end

Per verificare tutta l'API in locale con server reale:

```bash
# Terminale 1 — avvia server
FR_API_TOKEN=changeme python api_server.py

# Terminale 2 — esegui smoke test
python smoke_test.py
```

Lo smoke test verifica:
- `/health` — stato e versione
- `/encode`, `/detect`, `/compare` — pipeline facciale base
- `/register`, `/known`, `/known/{id}` — gestione DB volti
- `/osint/image` — generazione link e metadata OSINT
- `/report/pdf` — generazione PDF reale (`smoke_test_report.pdf` salvato su disco).

---

## REST API

### Endpoint HTTP completi

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST` | `/encode` | Encoding facciale da immagine |
| `POST` | `/detect` | Rilevamento volti (solo bounding box) |
| `POST` | `/compare` | Confronto tra due encoding |
| `POST` | `/register` | Registra volto noto nel DB |
| `GET`  | `/known` | Lista volti noti |
| `DELETE` | `/known/{id}` | Elimina volto noto |
| `POST` | `/osint/image` | Reverse image search |
| `POST` | `/osint/social` | Ricerca social per nome/username |
| `POST` | `/osint/full` | Pipeline OSINT completa (JSON) |
| `POST` | `/report/pdf` | Pipeline OSINT + PDF scaricabile |
| `GET`  | `/health` | Health check |

### Endpoint WebSocket

| Endpoint | Descrizione |
|----------|-------------|
| `WS /ws/stream` | Stream webcam dal browser (frame JPEG base64) |
| `WS /ws/rtsp?url=...` | Stream da IP camera o RTSP tramite OpenCV |

---

## Utilizzo API Python (compatibile con originale)

```python
import face_recognition

immagine_a = face_recognition.load_image_file("persona_a.jpg")
encoding_a = face_recognition.face_encodings(immagine_a)[0]

immagine_b = face_recognition.load_image_file("persona_b.jpg")
encoding_b = face_recognition.face_encodings(immagine_b)[0]

risultato = face_recognition.compare_faces([encoding_a], encoding_b)
print(risultato)  # [True] oppure [False]
```

---

## Docker

```bash
docker build -t face-recognition-ng .
docker run -p 8000:8000 -e FR_API_TOKEN=il_tuo_token face-recognition-ng
```

---

## Struttura del progetto

```
face_recognition/
├── face_recognition/
│   ├── __init__.py                    # Entry point API pubblica
│   └── backends/
│       └── insightface_backend.py     # Backend InsightFace (sostituisce dlib)
├── dashboard/
│   └── index.html                     # Dashboard web (webcam + RTSP + PDF report)
├── tests/
│   ├── conftest.py                    # Fixture condivise (TestClient, mock)
│   ├── test_api_core.py               # Test endpoint core (encode, detect, compare)
│   ├── test_api_osint.py              # Test endpoint OSINT
│   ├── test_report_pdf.py             # Test generatore PDF + endpoint /report/pdf
│   └── test_integration_real.py       # Test InsightFace reale con immagini vere
├── api_server.py                      # Server FastAPI + WebSocket + OSINT
├── report_generator.py                # Generatore PDF OSINT (dark design)
├── websocket_stream.py                # Gestore stream video WebSocket
├── face_db.py                         # Database SQLite volti noti
├── osint_engine.py                    # Reverse image search
├── social_lookup.py                   # Ricerca profili social + Google dorks
├── maigret_wrapper.py                 # Wrapper Maigret per username discovery
├── requirements_ng.txt                # Dipendenze aggiornate (stack completo)
├── requirements_test.txt              # Dipendenze leggere per test mockati
├── smoke_test.py                      # Smoke test end-to-end
└── examples/                          # Esempi di utilizzo
```

---

## Roadmap

- [x] **Fase 1** — Sostituzione dlib → InsightFace, API compatibile
- [x] **Fase 2** — REST API FastAPI con autenticazione token
- [x] **Fase 3** — Motore OSINT: reverse image search + social lookup + Maigret
- [x] **Fase 4** — Dashboard web con webcam live, stream RTSP, DB volti noti
- [x] **Fase 5** — Generazione automatica report PDF con grafici e tabelle
- [x] **Fase 6** — Test suite pytest + CI GitHub Actions (Python 3.10 / 3.11 / 3.12)
- [x] **Fase 7** — Test di integrazione reale + smoke test end-to-end + ENV tuning OSINT

---

## Note legali

> ⚠️ **Uso responsabile**: questo strumento è destinato esclusivamente a ricerche legali (OSINT difensivo, pentesting autorizzato, ricerca accademica). L'uso per sorveglianza non autorizzata di persone fisiche può violare il GDPR e le leggi sulla privacy locali. Usare sempre nel rispetto della normativa vigente.

---

## Differenze rispetto all'originale

| Caratteristica | ageitgey/face_recognition | face_recognition-ng |
|---|---|---|
| Backend | dlib (C++) | InsightFace (ONNX) |
| Python 3.12+ | ❌ Rotto | ✅ Supportato |
| GPU support | ❌ No | ✅ CUDA |
| Embedding | 128D | 512D |
| REST API | ❌ No | ✅ FastAPI |
| Dashboard web | ❌ No | ✅ Inclusa |
| Webcam live | ❌ No | ✅ WebSocket |
| Stream RTSP | ❌ No | ✅ OpenCV |
| Database volti | ❌ No | ✅ SQLite |
| Reverse image search | ❌ No | ✅ Google Lens, Yandex, TinEye |
| Social lookup | ❌ No | ✅ Instagram, Twitter, LinkedIn, FB, TikTok |
| Username discovery | ❌ No | ✅ Maigret (3000+ siti) |
| Report PDF | ❌ No | ✅ Dark design + grafici |
| Test suite | ❌ No | ✅ pytest (3.10 / 3.11 / 3.12) |
| CI/CD | ❌ No | ✅ GitHub Actions (unit + integration real) |
| Installazione | Complessa (C++) | Semplice (pip) |

---

## Crediti

- Libreria originale: [ageitgey/face_recognition](https://github.com/ageitgey/face_recognition) di Adam Geitgey
- Nuovo backend: [InsightFace](https://github.com/deepinsight/insightface)
- OSINT username discovery: [Maigret](https://github.com/soxoj/maigret) di soxoj
- Fork e nuove funzionalità: [Lorenzozero](https://github.com/Lorenzozero)

---

## Licenza

MIT — vedi [LICENSE](LICENSE)
