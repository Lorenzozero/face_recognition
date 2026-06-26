"""
face_recognition-ng — FastAPI REST + WebSocket Server
Espone riconoscimento facciale via HTTP e WebSocket.

Endpoint HTTP:
  POST /encode        — encoding da immagine
  POST /detect        — rilevamento volti
  POST /compare       — confronto encoding
  POST /register      — registra volto noto nel DB
  GET  /known         — lista volti noti
  DELETE /known/{id}  — elimina volto noto
  GET  /health        — health check

Endpoint WebSocket:
  WS /ws/stream       — stream webcam dal browser
  WS /ws/rtsp         — stream da IP camera/RTSP

Usage:
  FR_API_TOKEN=secret python api_server.py
  Swagger UI: http://localhost:8000/docs
"""

import os
import io
import numpy as np
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, WebSocket, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
import PIL.Image

import face_recognition
from face_db import FaceDatabase
from websocket_stream import handle_webcam_stream, handle_rtsp_stream

# — Auth —
API_TOKEN = os.environ.get("FR_API_TOKEN", "changeme")
security = HTTPBearer(auto_error=False)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials or credentials.credentials != API_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")
    return credentials.credentials

# — App —
app = FastAPI(
    title="face_recognition-ng API",
    description="Riconoscimento facciale via REST e WebSocket. Fork di ageitgey/face_recognition.",
    version="3.0.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Serve la dashboard web
if os.path.exists("dashboard"):
    app.mount("/dashboard", StaticFiles(directory="dashboard", html=True), name="dashboard")

db = FaceDatabase()

# — Modelli Pydantic —
class CompareRequest(BaseModel):
    encoding_a: List[float]
    encoding_b: List[float]
    tolerance: float = 0.5

class CompareResponse(BaseModel):
    match: bool
    distance: float

class EncodeResponse(BaseModel):
    faces_found: int
    encodings: List[List[float]]
    locations: List[List[int]]

class DetectResponse(BaseModel):
    faces_found: int
    locations: List[List[int]]

class RegisterResponse(BaseModel):
    id: int
    name: str
    message: str

class KnownFace(BaseModel):
    id: int
    name: str
    created_at: str

# — Helper —
def load_image_from_upload(file: UploadFile) -> np.ndarray:
    contents = file.file.read()
    image = PIL.Image.open(io.BytesIO(contents)).convert("RGB")
    return np.array(image)

# — Endpoint HTTP —
@app.get("/health")
def health():
    return {"status": "ok", "version": "3.0.0"}

@app.get("/", include_in_schema=False)
def root():
    return FileResponse("dashboard/index.html") if os.path.exists("dashboard/index.html") else {"msg": "face_recognition-ng v3"}

@app.post("/encode", response_model=EncodeResponse)
def encode_face(file: UploadFile = File(...), token: str = Depends(verify_token)):
    """Carica un'immagine e ottieni encoding + bounding box dei volti trovati."""
    img = load_image_from_upload(file)
    locations = face_recognition.face_locations(img)
    encodings = face_recognition.face_encodings(img)
    return EncodeResponse(
        faces_found=len(encodings),
        encodings=[e.tolist() for e in encodings],
        locations=[list(loc) for loc in locations],
    )

@app.post("/detect", response_model=DetectResponse)
def detect_faces(file: UploadFile = File(...), token: str = Depends(verify_token)):
    """Rileva volti in un'immagine. Più veloce di /encode (nessun embedding)."""
    img = load_image_from_upload(file)
    locations = face_recognition.face_locations(img)
    return DetectResponse(faces_found=len(locations), locations=[list(loc) for loc in locations])

@app.post("/compare", response_model=CompareResponse)
def compare_faces(body: CompareRequest, token: str = Depends(verify_token)):
    """Confronta due encoding facciali. Restituisce match e distanza."""
    enc_a = np.array(body.encoding_a)
    enc_b = np.array(body.encoding_b)
    distances = face_recognition.face_distance([enc_a], enc_b)
    distance = float(distances[0])
    return CompareResponse(match=distance <= body.tolerance, distance=round(distance, 4))

@app.post("/register", response_model=RegisterResponse)
def register_face(
    name: str,
    file: UploadFile = File(...),
    token: str = Depends(verify_token),
):
    """Registra un volto noto nel database SQLite per il riconoscimento in tempo reale."""
    img = load_image_from_upload(file)
    encodings = face_recognition.face_encodings(img)
    if not encodings:
        raise HTTPException(status_code=400, detail="Nessun volto trovato nell'immagine")
    face_id = db.register(name, encodings[0])
    return RegisterResponse(id=face_id, name=name, message=f"Volto di '{name}' registrato con ID {face_id}")

@app.get("/known", response_model=List[KnownFace])
def list_known_faces(token: str = Depends(verify_token)):
    """Restituisce la lista di tutti i volti noti registrati nel database."""
    return db.list_known()

@app.delete("/known/{face_id}")
def delete_known_face(face_id: int, token: str = Depends(verify_token)):
    """Elimina un volto noto dal database."""
    db.delete(face_id)
    return {"message": f"Volto ID {face_id} eliminato"}

# — Endpoint WebSocket —
@app.websocket("/ws/stream")
async def websocket_webcam(websocket: WebSocket):
    """Stream webcam dal browser. Invia frame JPEG base64, ricevi bounding box in JSON."""
    await handle_webcam_stream(websocket)

@app.websocket("/ws/rtsp")
async def websocket_rtsp(websocket: WebSocket, url: str = Query(...)):
    """Stream da IP camera o RTSP. Parametro: ?url=rtsp://..."""
    await handle_rtsp_stream(websocket, url)


if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
