"""
face_recognition-ng — FastAPI REST Server
Exposes face recognition features over HTTP with token authentication.

Usage:
    python api_server.py
    # Swagger UI: http://localhost:8000/docs

Auth:
    Set env var FR_API_TOKEN=your_secret_token
    Pass header: Authorization: Bearer your_secret_token
"""

import os
import io
import numpy as np
from typing import List

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import PIL.Image

import face_recognition

# ── Auth ──────────────────────────────────────────────────────────────────────
API_TOKEN = os.environ.get("FR_API_TOKEN", "changeme")
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != API_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return credentials.credentials

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="face_recognition-ng API",
    description="REST API for face detection, encoding and comparison. Fork of ageitgey/face_recognition.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models ────────────────────────────────────────────────────────────────────
class CompareRequest(BaseModel):
    encoding_a: List[float]
    encoding_b: List[float]
    tolerance: float = 0.6

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

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_image_from_upload(file: UploadFile) -> np.ndarray:
    contents = file.file.read()
    image = PIL.Image.open(io.BytesIO(contents)).convert("RGB")
    return np.array(image)

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


@app.post("/encode", response_model=EncodeResponse)
def encode_face(
    file: UploadFile = File(...),
    token: str = Depends(verify_token),
):
    """Upload an image and get face encodings + locations."""
    img = load_image_from_upload(file)
    locations = face_recognition.face_locations(img)
    encodings = face_recognition.face_encodings(img)
    return EncodeResponse(
        faces_found=len(encodings),
        encodings=[e.tolist() for e in encodings],
        locations=[list(loc) for loc in locations],
    )


@app.post("/detect", response_model=DetectResponse)
def detect_faces(
    file: UploadFile = File(...),
    token: str = Depends(verify_token),
):
    """Detect faces in an image. Returns bounding boxes only (faster than /encode)."""
    img = load_image_from_upload(file)
    locations = face_recognition.face_locations(img)
    return DetectResponse(
        faces_found=len(locations),
        locations=[list(loc) for loc in locations],
    )


@app.post("/compare", response_model=CompareResponse)
def compare_faces(
    body: CompareRequest,
    token: str = Depends(verify_token),
):
    """Compare two face encodings. Returns match (bool) and distance (float)."""
    enc_a = np.array(body.encoding_a)
    enc_b = np.array(body.encoding_b)
    distances = face_recognition.face_distance([enc_a], enc_b)
    distance = float(distances[0])
    match = bool(distance <= body.tolerance)
    return CompareResponse(match=match, distance=round(distance, 4))


if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
