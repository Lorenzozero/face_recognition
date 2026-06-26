# face_recognition-ng

> ⚡ A modern fork of [ageitgey/face_recognition](https://github.com/ageitgey/face_recognition) — same simple API, modern backend.

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Fork of ageitgey/face_recognition](https://img.shields.io/badge/fork-ageitgey%2Fface__recognition-lightgrey)](https://github.com/ageitgey/face_recognition)

---

## Why this fork?

The original [face_recognition](https://github.com/ageitgey/face_recognition) by Adam Geitgey is one of the most starred facial recognition libraries on GitHub (50k+ ⭐). However it relies on **dlib**, which:

- Requires painful C++ compilation
- Is broken on Python 3.12+
- Lacks native GPU support
- Uses a model from 2017

This fork keeps the **exact same simple API** while replacing the backend with [InsightFace](https://github.com/deepinsight/insightface), a state-of-the-art face recognition library with:

- ✅ Python 3.9–3.12+ support
- ✅ Native GPU (CUDA) support
- ✅ +15% accuracy over dlib on standard benchmarks
- ✅ No C++ compilation required
- ✅ Drop-in replacement — zero code changes needed

---

## Installation

```bash
pip install -r requirements_ng.txt
```

For GPU support:
```bash
pip install onnxruntime-gpu  # instead of onnxruntime
```

---

## Usage (same API as original)

```python
import face_recognition

# Load images
image_a = face_recognition.load_image_file("person_a.jpg")
image_b = face_recognition.load_image_file("person_b.jpg")

# Get face encodings
encoding_a = face_recognition.face_encodings(image_a)[0]
encoding_b = face_recognition.face_encodings(image_b)[0]

# Compare faces
result = face_recognition.compare_faces([encoding_a], encoding_b)
print(result)  # [True] or [False]

# Detect face locations
locations = face_recognition.face_locations(image_a)
print(locations)  # [(top, right, bottom, left), ...]
```

---

## REST API (New in this fork)

This fork ships a **FastAPI server** to expose all features over HTTP:

```bash
python api_server.py
# Swagger UI available at http://localhost:8000/docs
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/encode` | Upload an image, get face encodings |
| `POST` | `/compare` | Compare two encodings, get similarity score |
| `POST` | `/detect` | Detect faces, get bounding boxes |
| `GET`  | `/health` | Health check |

### Example

```bash
curl -X POST http://localhost:8000/encode \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@photo.jpg"
```

---

## Roadmap

- [x] **Phase 1** — Replace dlib with InsightFace, keep API compatible
- [x] **Phase 2** — FastAPI REST server with token auth
- [ ] **Phase 3** — OSINT integration: match a face against scraped public profiles (Maigret integration)
- [ ] **Phase 4** — Web dashboard (React/Next.js) with drag & drop, bounding boxes, confidence scores
- [ ] **Phase 5** — PDF report generation from recognition results

---

## Docker

```bash
docker build -t face-recognition-ng .
docker run -p 8000:8000 face-recognition-ng
```

---

## Credits

- Original library: [ageitgey/face_recognition](https://github.com/ageitgey/face_recognition) by Adam Geitgey
- New backend: [InsightFace](https://github.com/deepinsight/insightface)
- Fork & new features: [Lorenzozero](https://github.com/Lorenzozero)

---

## License

MIT — see [LICENSE](LICENSE)
