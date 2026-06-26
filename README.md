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

Questo fork mantiene la **stessa API semplicissima** dell'originale, sostituendo il backend con [InsightFace](https://github.com/deepinsight/insightface), una libreria di riconoscimento facciale allo stato dell'arte.

### Vantaggi rispetto all'originale

- ✅ Compatibile con Python 3.9–3.12+
- ✅ Supporto GPU nativo (CUDA) tramite ONNX Runtime
- ✅ Accuratezza superiore del ~15% rispetto a dlib sui benchmark standard
- ✅ Nessuna compilazione C++ richiesta
- ✅ Drop-in replacement — zero modifiche al codice esistente
- ✅ REST API HTTP integrata (nuova funzionalità)

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

## Utilizzo (API identica all'originale)

```python
import face_recognition

# Carica le immagini
immagine_a = face_recognition.load_image_file("persona_a.jpg")
immagine_b = face_recognition.load_image_file("persona_b.jpg")

# Calcola gli encoding facciali
encoding_a = face_recognition.face_encodings(immagine_a)[0]
encoding_b = face_recognition.face_encodings(immagine_b)[0]

# Confronta i volti
risultato = face_recognition.compare_faces([encoding_a], encoding_b)
print(risultato)  # [True] oppure [False]

# Rileva le posizioni dei volti
posizioni = face_recognition.face_locations(immagine_a)
print(posizioni)  # [(top, right, bottom, left), ...]
```

---

## REST API (nuova in questo fork)

Questo fork include un **server FastAPI** per esporre tutte le funzionalità via HTTP:

```bash
FR_API_TOKEN=il_tuo_token python api_server.py
# Swagger UI disponibile su http://localhost:8000/docs
```

### Endpoint disponibili

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST` | `/encode` | Carica un'immagine, ricevi encoding + bounding box |
| `POST` | `/compare` | Confronta due encoding, ottieni score di similarità |
| `POST` | `/detect` | Rileva volti, restituisce solo le bounding box (più veloce) |
| `GET`  | `/health` | Controllo stato del server |

### Esempio con curl

```bash
curl -X POST http://localhost:8000/encode \
  -H "Authorization: Bearer il_tuo_token" \
  -F "file=@foto.jpg"
```

Autenticazione tramite header `Authorization: Bearer <token>`. Il token si imposta con la variabile d'ambiente `FR_API_TOKEN`.

---

## Docker

```bash
docker build -t face-recognition-ng .
docker run -p 8000:8000 -e FR_API_TOKEN=il_tuo_token face-recognition-ng
```

---

## Roadmap

Queste sono le modifiche pianificate rispetto al progetto originale:

- [x] **Fase 1** — Sostituzione di dlib con InsightFace mantenendo la compatibilità API
- [x] **Fase 2** — Server REST FastAPI con autenticazione token
- [ ] **Fase 3** — Integrazione OSINT: dato un volto, cerca corrispondenze in profili pubblici (integrazione con [Maigret](https://github.com/soxoj/maigret))
- [ ] **Fase 4** — Dashboard web (React/Next.js) con drag & drop, visualizzazione bounding box e confidence score
- [ ] **Fase 5** — Generazione automatica di report PDF dai risultati del riconoscimento

---

## Struttura del progetto

```
face_recognition/
├── face_recognition/
│   ├── __init__.py                    # Entry point, espone l'API pubblica
│   └── backends/
│       └── insightface_backend.py     # Nuovo backend InsightFace (sostituisce dlib)
├── api_server.py                      # Server FastAPI REST (nuovo)
├── requirements_ng.txt                # Dipendenze aggiornate (senza dlib)
├── requirements.txt                   # Dipendenze originali (mantenute per compatibilità)
├── Dockerfile                         # Docker support
└── examples/                          # Esempi di utilizzo
```

---

## Differenze rispetto all'originale

| Caratteristica | ageitgey/face_recognition | face_recognition-ng (questo fork) |
|---|---|---|
| Backend | dlib (C++) | InsightFace (ONNX) |
| Python 3.12+ | ❌ Rotto | ✅ Supportato |
| GPU support | ❌ No | ✅ CUDA via ONNX Runtime |
| Dimensione embedding | 128D | 512D (più accurato) |
| REST API | ❌ No | ✅ FastAPI inclusa |
| Installazione | Complessa (build C++) | Semplice (`pip install`) |
| Compatibilità API | — | ✅ 100% compatibile |

---

## Crediti

- Libreria originale: [ageitgey/face_recognition](https://github.com/ageitgey/face_recognition) di Adam Geitgey
- Nuovo backend: [InsightFace](https://github.com/deepinsight/insightface)
- Fork e nuove funzionalità: [Lorenzozero](https://github.com/Lorenzozero)

---

## Licenza

MIT — vedi [LICENSE](LICENSE)
