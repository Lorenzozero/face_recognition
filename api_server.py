"""
face_recognition-ng — FastAPI REST + WebSocket Server
Espone riconoscimento facciale via HTTP e WebSocket.

Endpoint HTTP:
  POST /encode          — encoding da immagine
  POST /detect          — rilevamento volti
  POST /compare         — confronto encoding
  POST /register        — registra volto noto nel DB
  GET  /known           — lista volti noti
  DELETE /known/{id}    — elimina volto noto
  POST /osint/image     — reverse image search (con caching)
  POST /osint/social    — ricerca social per nome/username
  POST /osint/full      — pipeline OSINT completa (con caching + risk_score)
  POST /report/pdf      — genera PDF OSINT completo (con risk_score)
  GET  /osint/stats     — statistiche e ultime run OSINT
  GET  /health          — health check

Endpoint WebSocket:
  WS /ws/stream         — stream webcam dal browser
  WS /ws/rtsp           — stream da IP camera/RTSP

Usage:
  FR_API_TOKEN=secret python api_server.py
  Swagger UI: http://localhost:8000/docs
"""

import os
import io
import json
import numpy as np
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, WebSocket, Query, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
import uvicorn
import PIL.Image

import face_recognition
from face_db import FaceDatabase
from websocket_stream import handle_webcam_stream, handle_rtsp_stream
from osint_engine import OsintEngine
from social_lookup import SocialLookup
from maigret_wrapper import MaigretWrapper
from report_generator import build_pdf
from osint_db import OsintDatabase

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
    description="Riconoscimento facciale + OSINT via REST e WebSocket.",
    version="4.2.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

if os.path.exists("dashboard"):
    app.mount("/dashboard", StaticFiles(directory="dashboard", html=True), name="dashboard")

db = FaceDatabase()
osint = OsintEngine()
social = SocialLookup()
maigret = MaigretWrapper()
osint_db = OsintDatabase()

# — Modelli —
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

class OsintSearchRequest(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    run_maigret: bool = False

# — Helper —

def load_image_from_upload(file: UploadFile) -> np.ndarray:
    contents = file.file.read()
    image = PIL.Image.open(io.BytesIO(contents)).convert("RGB")
    return np.array(image)


def image_to_bytes(file: UploadFile) -> bytes:
    file.file.seek(0)
    return file.file.read()


def _build_evidence_from_reverse(reverse: dict) -> List[dict]:
    evidence = []
    sources = reverse.get("sources", {})
    for src_name, src_data in sources.items():
        for r in src_data.get("results", []):
            evidence.append({
                "source": src_name,
                "url": r.get("url", ""),
                "kind": "reverse_image",
                "confidence": 0.5,
                "meta": {
                    "title": r.get("title"),
                },
            })
    return evidence


def _compute_risk_score(osint_data: dict) -> float:
    """Calcolo semplice di risk_score: numero profili social trovati / 10 (max 1.0)."""
    social = osint_data.get("social") or {}
    profiles = social.get("platforms") or []
    found_count = sum(1 for p in profiles if p.get("found"))
    score = min(1.0, found_count / 10.0)
    return float(score)


# — Health & root —
@app.get("/health")
def health():
    return {"status": "ok", "version": "4.2.0"}


@app.get("/", include_in_schema=False)
def root():
    return FileResponse("dashboard/index.html") if os.path.exists("dashboard/index.html") else {"msg": "face_recognition-ng v4.2"}


# — Endpoint core riconoscimento —
@app.post("/encode", response_model=EncodeResponse)
def encode_face(file: UploadFile = File(...), token: str = Depends(verify_token)):
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
    img = load_image_from_upload(file)
    locations = face_recognition.face_locations(img)
    return DetectResponse(faces_found=len(locations), locations=[list(loc) for loc in locations])


@app.post("/compare", response_model=CompareResponse)
def compare_faces(body: CompareRequest, token: str = Depends(verify_token)):
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
    img = load_image_from_upload(file)
    encodings = face_recognition.face_encodings(img)
    if not encodings:
        raise HTTPException(status_code=400, detail="Nessun volto trovato nell'immagine")
    face_id = db.register(name, encodings[0])
    return RegisterResponse(id=face_id, name=name, message=f"Volto di '{name}' registrato con ID {face_id}")


@app.get("/known", response_model=List[KnownFace])
def list_known_faces(token: str = Depends(verify_token)):
    return db.list_known()


@app.delete("/known/{face_id}")
def delete_known_face(face_id: int, token: str = Depends(verify_token)):
    db.delete(face_id)
    return {"message": f"Volto ID {face_id} eliminato"}


# — Endpoint OSINT —

@app.post("/osint/image")
async def osint_image_search(
    file: UploadFile = File(...),
    token: str = Depends(verify_token),
):
    """Ricerca reverse image del volto su Google Lens, Yandex, TinEye, PimEyes, con caching per image_hash."""
    contents = await file.read()
    img_array = np.array(PIL.Image.open(io.BytesIO(contents)).convert("RGB"))
    locations = face_recognition.face_locations(img_array)

    # Caching per image_hash
    image_hash = None
    try:
        import hashlib
        image_hash = hashlib.md5(contents).hexdigest()[:8]
    except Exception:
        pass

    if image_hash:
        existing_runs = osint_db.get_runs_by_image_hash(image_hash)
        if existing_runs:
            # Usa l'ultima run salvata come cache
            cached = osint_db.load_raw_run(existing_runs[0]["id"])
            if cached:
                cached["faces_detected"] = len(locations)
                cached["from_cache"] = True
                return cached

    face_bytes = contents
    if locations:
        top, right, bottom, left = locations[0]
        h, w = img_array.shape[:2]
        pad = 30
        top = max(0, top - pad)
        left = max(0, left - pad)
        bottom = min(h, bottom + pad)
        right = min(w, right + pad)
        face_crop = PIL.Image.fromarray(img_array[top:bottom, left:right])
        buf = io.BytesIO()
        face_crop.save(buf, format="JPEG", quality=90)
        face_bytes = buf.getvalue()

    reverse = await osint.search(face_bytes)
    reverse["faces_detected"] = len(locations)
    reverse["face_cropped"] = len(locations) > 0

    image_hash = reverse.get("image_hash") or image_hash or ""
    run_id = osint_db.save_run(image_hash, target_name="", run_type="image", raw_json=reverse)
    evidence = _build_evidence_from_reverse(reverse)
    if evidence:
        osint_db.save_evidence_batch(run_id, evidence)

    reverse["from_cache"] = False
    return reverse


@app.post("/osint/social")
async def osint_social_search(
    body: OsintSearchRequest,
    token: str = Depends(verify_token),
):
    """Cerca profili social dato un nome e/o username. Può usare Maigret."""
    result = {}

    if body.name:
        result["by_name"] = await social.search_by_name(body.name)
        result["osint_links"] = social.generate_osint_report_links(
            body.name, body.username
        )

    if body.username:
        result["by_username"] = await social.search_by_username(body.username)
        if body.run_maigret:
            result["maigret"] = await maigret.search(body.username)

    if body.name and not body.username:
        variants = maigret.generate_username_variants(body.name)
        result["username_variants"] = variants
        if body.run_maigret and variants:
            result["maigret"] = await maigret.search_multiple(variants[:5])

    return result


@app.post("/osint/full")
async def osint_full(
    name: str = Form(...),
    file: UploadFile = File(...),
    run_maigret: bool = Form(False),
    token: str = Depends(verify_token),
):
    """Pipeline OSINT completa (reverse image + social + Maigret opzionale) con caching e risk_score."""
    contents = await file.read()
    img_array = np.array(PIL.Image.open(io.BytesIO(contents)).convert("RGB"))
    locations = face_recognition.face_locations(img_array)

    # Caching per image_hash
    image_hash = None
    try:
        import hashlib
        image_hash = hashlib.md5(contents).hexdigest()[:8]
    except Exception:
        pass

    if image_hash:
        existing_runs = osint_db.get_runs_by_image_hash(image_hash)
        for r in existing_runs:
            if r["run_type"] == "full":
                cached = osint_db.load_raw_run(r["id"])
                if cached:
                    cached["faces_detected"] = len(locations)
                    cached["from_cache"] = True
                    return cached

    reverse = await osint.search(contents)
    social_results = await social.search_by_name(name)
    osint_links = social.generate_osint_report_links(name)
    variants = maigret.generate_username_variants(name)

    maigret_results = None
    if run_maigret and variants:
        maigret_results = await maigret.search_multiple(variants[:3])

    osint_data = {
        "target_name": name,
        "faces_detected": len(locations),
        "reverse_image": reverse,
        "social": social_results,
        "osint_links": osint_links,
        "username_variants": variants,
        "maigret": maigret_results,
    }

    risk_score = _compute_risk_score(osint_data)

    image_hash = reverse.get("image_hash") or image_hash or ""
    run_id = osint_db.save_run(image_hash, target_name=name, run_type="full", raw_json=osint_data, risk_score=risk_score)
    evidence = _build_evidence_from_reverse(reverse)
    if evidence:
        osint_db.save_evidence_batch(run_id, evidence)

    osint_data["risk_score"] = risk_score
    osint_data["from_cache"] = False
    return osint_data


# — Endpoint Report PDF —

@app.post(
    "/report/pdf",
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF OSINT report scaricabile",
        }
    },
)
async def generate_pdf_report(
    name: str = Form(..., description="Nome del target OSINT"),
    file: UploadFile = File(..., description="Immagine con il volto del target"),
    run_maigret: bool = Form(False, description="Esegui Maigret per username discovery"),
    token: str = Depends(verify_token),
):
    """Pipeline OSINT completa + generazione PDF + salvataggio strutturato in DB OSINT con risk_score."""
    contents = await file.read()
    img_array = np.array(PIL.Image.open(io.BytesIO(contents)).convert("RGB"))
    locations = face_recognition.face_locations(img_array)

    face_bytes = None
    if locations:
        top, right, bottom, left = locations[0]
        h, w = img_array.shape[:2]
        pad = 30
        face_crop = PIL.Image.fromarray(
            img_array[max(0, top-pad):min(h, bottom+pad),
                      max(0, left-pad):min(w, right+pad)]
        )
        buf = io.BytesIO()
        face_crop.save(buf, format="JPEG", quality=90)
        face_bytes = buf.getvalue()

    reverse = await osint.search(contents)
    social_results = await social.search_by_name(name)
    osint_links = social.generate_osint_report_links(name)
    variants = maigret.generate_username_variants(name)

    maigret_results = None
    if run_maigret and variants:
        maigret_results = await maigret.search_multiple(variants[:3])

    osint_data = {
        "target_name": name,
        "faces_detected": len(locations),
        "reverse_image": reverse,
        "social": social_results,
        "osint_links": osint_links,
        "username_variants": variants,
        "maigret": maigret_results,
    }

    risk_score = _compute_risk_score(osint_data)

    image_hash = reverse.get("image_hash") or ""
    run_id = osint_db.save_run(image_hash, target_name=name, run_type="pdf", raw_json=osint_data, risk_score=risk_score)
    evidence = _build_evidence_from_reverse(reverse)
    if evidence:
        osint_db.save_evidence_batch(run_id, evidence)

    osint_data["risk_score"] = risk_score

    pdf_bytes = build_pdf(osint_data, face_bytes)

    safe_name = name.replace(" ", "_").lower()
    filename = f"osint_report_{safe_name}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# — OSINT stats —
@app.get("/osint/stats")
async def osint_stats(token: str = Depends(verify_token)):
    """Statistiche di base e ultime run OSINT (per dashboard/monitoring)."""
    runs = osint_db.get_recent_runs(limit=20)
    return {
        "recent_runs": runs,
    }


# — WebSocket —
@app.websocket("/ws/stream")
async def websocket_webcam(websocket: WebSocket):
    await handle_webcam_stream(websocket)


@app.websocket("/ws/rtsp")
async def websocket_rtsp(websocket: WebSocket, url: str = Query(...)):
    await handle_rtsp_stream(websocket, url)


if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
