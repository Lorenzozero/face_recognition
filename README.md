# face_recognition-ng

> ⚡ Fork moderno di [ageitgey/face_recognition](https://github.com/ageitgey/face_recognition) — stessa API semplice, backend aggiornato.

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

Questo fork mantiene la **stessa API semplicissima** dell'originale, sostituendo il backend con [InsightFace](https://github.com/deepinsight/insightface).

### Vantaggi rispetto all'originale

- ✅ Compatibile con Python 3.9–3.12+
- ✅ Supporto GPU nativo (CUDA) tramite ONNX Runtime
- ✅ Accuratezza superiore del ~15% rispetto a dlib
- ✅ Nessuna compilazione C++ richiesta
- ✅ Drop-in replacement — zero modifiche al codice esistente
- ✅ REST API HTTP integrata
- ✅ Dashboard web con webcam live e stream RTSP
- ✅ Database volti noti (SQLite)

---

## Installazione

```bash
git clone https://github.com/Lorenzozero/face_recognition
cd face_recognition
pip install -r requirements_ng.txt
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
- 📊 **Log eventi** — storico dei riconoscimenti in tempo reale

---

## REST API

```bash
FR_API_TOKEN=il_tuo_token python api_server.py
# Swagger UI: http://localhost:8000/docs
```

### Endpoint HTTP

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST` | `/encode` | Encoding facciale da immagine |
| `POST` | `/detect` | Rilevamento volti (solo bounding box) |
| `POST` | `/compare` | Confronto tra due encoding |
| `POST` | `/register` | Registra volto noto nel DB |
| `GET`  | `/known` | Lista volti noti |
| `DELETE` | `/known/{id}` | Elimina volto noto |
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
│   └── index.html                     # Dashboard web (webcam + RTSP + DB)
├── api_server.py                      # Server FastAPI + WebSocket
├── websocket_stream.py               # Gestore stream video WebSocket
├── face_db.py                         # Database SQLite volti noti
├── requirements_ng.txt                # Dipendenze aggiornate
└── examples/                          # Esempi di utilizzo
```

---

## Roadmap

- [x] **Fase 1** — Sostituzione dlib → InsightFace, API compatibile
- [x] **Fase 2** — REST API FastAPI con autenticazione token
- [x] **Fase 4** — Dashboard web con webcam live, stream RTSP, DB volti noti
- [ ] **Fase 3** — Integrazione OSINT: dato un volto, cerca corrispondenze in profili pubblici ([Maigret](https://github.com/soxoj/maigret))
- [ ] **Fase 5** — Generazione automatica report PDF

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
| Installazione | Complessa (C++) | Semplice (pip) |

---

## Crediti

- Libreria originale: [ageitgey/face_recognition](https://github.com/ageitgey/face_recognition) di Adam Geitgey
- Nuovo backend: [InsightFace](https://github.com/deepinsight/insightface)
- Fork e nuove funzionalità: [Lorenzozero](https://github.com/Lorenzozero)

---

## Licenza

MIT — vedi [LICENSE](LICENSE)
