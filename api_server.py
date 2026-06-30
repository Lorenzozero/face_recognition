"""
face_recognition-ng — FastAPI REST + WebSocket Server v4.6.3
Espone riconoscimento facciale via HTTP e WebSocket.

Endpoint HTTP:
  POST /encode             — encoding da immagine
  POST /detect             — rilevamento volti
  POST /compare            — confronto encoding
  POST /register           — registra volto noto nel DB
  GET  /known              — lista volti noti
  DELETE /known/{id}       — elimina volto noto
  POST /osint/image        — reverse image search (rate: 3/60s, cache TTL 24h)
  POST /osint/social       — ricerca social per nome/username (rate: 10/60s)
  POST /osint/full         — pipeline OSINT completa (rate: 2/60s)
  POST /report/pdf         — genera PDF OSINT completo (rate: 2/60s)
  GET  /osint/stats        — statistiche aggregate + ultime run (rate: 20/60s)
  GET  /osint/graph/{id}   — export grafo nodi/archi per una run (rate: 20/60s)
  GET  /health             — health check (no rate limit)

Variabili ENV:
  FR_API_TOKEN             token autenticazione (default: changeme)
  PORT                     porta su cui ascoltare (Railway la imposta automaticamente)
  OSINT_CACHE_TTL_HOURS    ore validita' cache OSINT (default: 24)
  RATE_LIMIT_ENABLED       true/false (default: true)
  RATE_LIMIT_WINDOW_SECS   finestra rate limit in secondi (default: 60)
  RATE_LIMIT_OSINT_IMAGE   max req /osint/image per finestra (default: 3)
  RATE_LIMIT_OSINT_FULL    max req /osint/full e /report/pdf (default: 2)
  RATE_LIMIT_OSINT_SOCIAL  max req /osint/social (default: 10)
  RATE_LIMIT_OSINT_STATS   max req /osint/stats e /osint/graph (default: 20)
  RATE_LIMIT_CLEANUP_SECS  intervallo cleanup rate limiter in secondi (default: 300)

Usage:
  FR_API_TOKEN=secret python api_server.py
  Swagger UI: http://localhost:8000/docs
"""

import os
import io
import json
import asyncio
import numpy as np
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, WebSocket, Query, Form, Request
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
from rate_limiter import RateLimiter, LIMIT_OSINT_IMAGE, LIMIT_OSINT_FULL, LIMIT_OSINT_SOCIAL, LIMIT_OSINT_STATS

RATE_LIMIT_CLEANUP_SECS = int(os.environ.get("RATE_LIMIT_CLEANUP_SECS", "300"))

# — Auth —
API_TOKEN = os.environ.get("FR_API_TOKEN", "changeme")
security = HTTPBearer(auto_error=False)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials or credentials.credentials != API_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")
    return credentials.credentials


# — Lifespan —
@asynccontextmanager
async def lifespan(app: FastAPI):
    async def _cleanup_loop():
        while True:
            await asyncio.sleep(RATE_LIMIT_CLEANUP_SECS)
            limiter.cleanup_expired()
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()


# — App —
app = FastAPI(
    title="face_recognition-ng API",
    description="Riconoscimento facciale + OSINT via REST e WebSocket.",
    version="4.6.3",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

if os.path.exists("dashboard"):
    app.mount("/dashboard", StaticFiles(directory="dashboard", html=True), name="dashboard")

db = FaceDatabase()
osint = OsintEngine()
social = SocialLookup()
maigret = MaigretWrapper()
osint_db = OsintDatabase()
limiter = RateLimiter()


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

def _safe_face_locations(img_array: np.ndarray) -> list:
    try:
        return face_recognition.face_locations(img_array)
    except Exception:
        return []


def _safe_face_encodings(img_array: np.ndarray, locations: list = None) -> list:
    try:
        if locations is not None:
            return face_recognition.face_encodings(img_array, locations)
        return face_recognition.face_encodings(img_array)
    except Exception:
        return []


def load_image_from_upload(file: UploadFile) -> np.ndarray:
    contents = file.file.read()
    image = PIL.Image.open(io.BytesIO(contents)).convert("RGB")
    return np.array(image)


def _get_image_hash(contents: bytes) -> str:
    import hashlib
    return hashlib.md5(contents).hexdigest()[:12]


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
                "meta": {"title": r.get("title")},
            })
    return evidence


def _build_evidence_from_social(social_data) -> List[dict]:
    """
    Gestisce tutti i formati possibili di SocialLookup:
      - search_by_name  -> {"platforms": {"instagram": {"results":[...]}, ...}}
      - search_by_username -> {"platforms": {"instagram": {"exists":True,"url":...}}, "found":[...]}
      - lista legacy [{"platform":..., "found":..., "url":...}]
    """
    evidence = []
    if not social_data:
        return evidence

    if isinstance(social_data, dict):
        platforms_raw = social_data.get("platforms", {})
        if isinstance(platforms_raw, dict):
            items = list(platforms_raw.values())
        elif isinstance(platforms_raw, list):
            items = platforms_raw
        else:
            items = []
    elif isinstance(social_data, list):
        items = social_data
    else:
        return evidence

    for item in items:
        if not isinstance(item, dict):
            continue
        # search_by_username: {"platform": ..., "url": ..., "exists": True}
        if item.get("exists") and item.get("url"):
            evidence.append({
                "source": item.get("platform", "social"),
                "url": item["url"],
                "kind": "social_profile",
                "confidence": 0.8,
                "meta": {"platform": item.get("platform")},
            })
        # search_by_name: {"platform": ..., "results": [{"url": ..., "title": ...}]}
        for r in item.get("results", []):
            if isinstance(r, dict) and r.get("url"):
                evidence.append({
                    "source": item.get("platform", "social"),
                    "url": r["url"],
                    "kind": "social_search",
                    "confidence": 0.5,
                    "meta": {"title": r.get("title"), "platform": item.get("platform")},
                })
    return evidence


def _build_evidence_from_maigret(maigret_data: dict) -> List[dict]:
    evidence = []
    if not maigret_data or not isinstance(maigret_data, dict):
        return evidence
    for username, data in maigret_data.items():
        results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for site in results:
            url = site.get("url", "")
            if url:
                evidence.append({
                    "source": f"maigret:{site.get('site', 'unknown')}",
                    "url": url,
                    "kind": "maigret_profile",
                    "confidence": 0.75,
                    "meta": {
                        "username": username,
                        "site": site.get("site"),
                        "category": site.get("category"),
                        "status": site.get("status"),
                    },
                })
    return evidence


def _compute_risk_score(osint_data: dict) -> float:
    social_d = osint_data.get("social") or {}
    platforms = social_d.get("platforms") or {}
    if isinstance(platforms, dict):
        found_social = sum(
            1 for v in platforms.values()
            if isinstance(v, dict) and (
                v.get("exists") or len(v.get("results", [])) > 0
            )
        )
    elif isinstance(platforms, list):
        found_social = sum(1 for p in platforms if isinstance(p, dict) and p.get("found"))
    else:
        found_social = 0
    social_score = min(1.0, found_social / 10.0) * 0.4

    maigret_d = osint_data.get("maigret") or {}
    maigret_hits = 0
    if isinstance(maigret_d, dict):
        for username, data in maigret_d.items():
            results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            maigret_hits += len(results)
    maigret_score = min(1.0, maigret_hits / 20.0) * 0.4

    reverse = osint_data.get("reverse_image") or {}
    sources = reverse.get("sources", {})
    rev_hits = sum(len(s.get("results", [])) for s in sources.values())
    reverse_score = min(1.0, rev_hits / 10.0) * 0.2

    return round(social_score + maigret_score + reverse_score, 3)


# — Health & root —
@app.get("/health")
def health():
    return {"status": "ok", "version": "4.6.3"}


@app.get("/", include_in_schema=False)
def root():
    return FileResponse("dashboard/index.html") if os.path.exists("dashboard/index.html") else {"msg": "face_recognition-ng v4.6.3"}


# — Endpoint core riconoscimento —
@app.post("/encode", response_model=EncodeResponse)
def encode_face(file: UploadFile = File(...), token: str = Depends(verify_token)):
    img = load_image_from_upload(file)
    locations = _safe_face_locations(img)
    encodings = _safe_face_encodings(img, locations)
    return EncodeResponse(
        faces_found=len(encodings),
        encodings=[e.tolist() for e in encodings],
        locations=[list(loc) for loc in locations],
    )


@app.post("/detect", response_model=DetectResponse)
def detect_faces(file: UploadFile = File(...), token: str = Depends(verify_token)):
    img = load_image_from_upload(file)
    locations = _safe_face_locations(img)
    return DetectResponse(faces_found=len(locations), locations=[list(loc) for loc in locations])


@app.post("/compare", response_model=CompareResponse)
def compare_faces(body: CompareRequest, token: str = Depends(verify_token)):
    enc_a = np.array(body.encoding_a)
    enc_b = np.array(body.encoding_b)
    try:
        distances = face_recognition.face_distance([enc_a], enc_b)
        distance = float(distances[0])
    except Exception:
        distance = 1.0
    return CompareResponse(match=distance <= body.tolerance, distance=round(distance, 4))


@app.post("/register", response_model=RegisterResponse)
def register_face(
    name: str,
    file: UploadFile = File(...),
    token: str = Depends(verify_token),
):
    img = load_image_from_upload(file)
    encodings = _safe_face_encodings(img)
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


# — OSINT —

@app.post("/osint/image")
async def osint_image_search(request: Request, file: UploadFile = File(...), token: str = Depends(verify_token)):
    limiter.check(request, tag="osint_image", limit=LIMIT_OSINT_IMAGE)
    contents = await file.read()
    try:
        img_array = np.array(PIL.Image.open(io.BytesIO(contents)).convert("RGB"))
        locations = _safe_face_locations(img_array)
    except Exception:
        img_array = None
        locations = []
    image_hash = _get_image_hash(contents)
    cached = osint_db.get_fresh_run(image_hash, run_type="image")
    if cached:
        cached["faces_detected"] = len(locations)
        cached["from_cache"] = True
        return cached
    face_bytes = contents
    if locations and img_array is not None:
        try:
            top, right, bottom, left = locations[0]
            h, w = img_array.shape[:2]
            pad = 30
            face_crop = PIL.Image.fromarray(img_array[max(0,top-pad):min(h,bottom+pad), max(0,left-pad):min(w,right+pad)])
            buf = io.BytesIO()
            face_crop.save(buf, format="JPEG", quality=90)
            face_bytes = buf.getvalue()
        except Exception:
            pass
    reverse = await osint.search(face_bytes)
    reverse["faces_detected"] = len(locations)
    reverse["face_cropped"] = len(locations) > 0
    reverse["from_cache"] = False
    run_id = osint_db.save_run(image_hash, target_name="", run_type="image", raw_json=reverse)
    evidence = _build_evidence_from_reverse(reverse)
    if evidence:
        osint_db.save_evidence_batch(run_id, evidence)
    return reverse


@app.post("/osint/social")
async def osint_social_search(request: Request, body: OsintSearchRequest, token: str = Depends(verify_token)):
    limiter.check(request, tag="osint_social", limit=LIMIT_OSINT_SOCIAL)
    result = {}
    image_hash = f"social:{body.name or ''}:{body.username or ''}"
    if body.name:
        result["by_name"] = await social.search_by_name(body.name)
        result["osint_links"] = social.generate_osint_report_links(body.name, body.username)
    if body.username:
        result["by_username"] = await social.search_by_username(body.username)
        if body.run_maigret:
            result["maigret"] = await maigret.search(body.username)
    if body.name and not body.username:
        variants = maigret.generate_username_variants(body.name)
        result["username_variants"] = variants
        if body.run_maigret and variants:
            result["maigret"] = await maigret.search_multiple(variants[:5])
    social_data = result.get("by_name") or result.get("by_username") or {}
    maigret_data = result.get("maigret") or {}
    evidence = _build_evidence_from_social(social_data) + _build_evidence_from_maigret(maigret_data)
    run_id = osint_db.save_run(image_hash, target_name=body.name or body.username or "", run_type="social", raw_json=result)
    if evidence:
        osint_db.save_evidence_batch(run_id, evidence)
    return result


@app.post("/osint/full")
async def osint_full(request: Request, name: str = Form(...), file: UploadFile = File(...), run_maigret: bool = Form(False), token: str = Depends(verify_token)):
    limiter.check(request, tag="osint_full", limit=LIMIT_OSINT_FULL)
    contents = await file.read()
    try:
        img_array = np.array(PIL.Image.open(io.BytesIO(contents)).convert("RGB"))
        locations = _safe_face_locations(img_array)
    except Exception:
        locations = []
    image_hash = _get_image_hash(contents)
    cached = osint_db.get_fresh_run(image_hash, run_type="full")
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
    osint_data = {"target_name": name, "faces_detected": len(locations), "reverse_image": reverse, "social": social_results, "osint_links": osint_links, "username_variants": variants, "maigret": maigret_results}
    risk_score = _compute_risk_score(osint_data)
    osint_data["risk_score"] = risk_score
    osint_data["from_cache"] = False
    run_id = osint_db.save_run(image_hash, target_name=name, run_type="full", raw_json=osint_data, risk_score=risk_score)
    evidence = _build_evidence_from_reverse(reverse) + _build_evidence_from_social(social_results) + _build_evidence_from_maigret(maigret_results or {})
    if evidence:
        osint_db.save_evidence_batch(run_id, evidence)
    osint_data["run_id"] = run_id
    return osint_data


@app.post("/report/pdf", response_class=Response, responses={200: {"content": {"application/pdf": {}}, "description": "PDF OSINT report"}})
async def generate_pdf_report(request: Request, name: str = Form(...), file: UploadFile = File(...), run_maigret: bool = Form(False), token: str = Depends(verify_token)):
    limiter.check(request, tag="report_pdf", limit=LIMIT_OSINT_FULL)
    contents = await file.read()
    try:
        img_array = np.array(PIL.Image.open(io.BytesIO(contents)).convert("RGB"))
        locations = _safe_face_locations(img_array)
    except Exception:
        img_array = None
        locations = []
    face_bytes = None
    if locations and img_array is not None:
        try:
            top, right, bottom, left = locations[0]
            h, w = img_array.shape[:2]
            pad = 30
            face_crop = PIL.Image.fromarray(img_array[max(0,top-pad):min(h,bottom+pad), max(0,left-pad):min(w,right+pad)])
            buf = io.BytesIO()
            face_crop.save(buf, format="JPEG", quality=90)
            face_bytes = buf.getvalue()
        except Exception:
            pass
    reverse = await osint.search(contents)
    social_results = await social.search_by_name(name)
    osint_links = social.generate_osint_report_links(name)
    variants = maigret.generate_username_variants(name)
    maigret_results = None
    if run_maigret and variants:
        maigret_results = await maigret.search_multiple(variants[:3])
    osint_data = {"target_name": name, "faces_detected": len(locations), "reverse_image": reverse, "social": social_results, "osint_links": osint_links, "username_variants": variants, "maigret": maigret_results}
    risk_score = _compute_risk_score(osint_data)
    osint_data["risk_score"] = risk_score
    image_hash = _get_image_hash(contents)
    run_id = osint_db.save_run(image_hash, target_name=name, run_type="pdf", raw_json=osint_data, risk_score=risk_score)
    evidence = _build_evidence_from_reverse(reverse) + _build_evidence_from_social(social_results) + _build_evidence_from_maigret(maigret_results or {})
    if evidence:
        osint_db.save_evidence_batch(run_id, evidence)
    pdf_bytes = build_pdf(osint_data, face_bytes)
    safe_name = name.replace(" ", "_").lower()
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="osint_report_{safe_name}.pdf"'})


@app.get("/osint/stats")
async def osint_stats(request: Request, token: str = Depends(verify_token)):
    limiter.check(request, tag="osint_stats", limit=LIMIT_OSINT_STATS)
    return {**osint_db.get_aggregate_stats(), "recent_runs": osint_db.get_recent_runs(limit=20)}


@app.get("/osint/graph/{run_id}")
async def osint_graph(run_id: int, request: Request, token: str = Depends(verify_token)):
    limiter.check(request, tag="osint_stats", limit=LIMIT_OSINT_STATS)
    graph = osint_db.get_graph(run_id)
    if not graph["nodes"]:
        raise HTTPException(status_code=404, detail=f"Run ID {run_id} non trovata")
    return graph


@app.websocket("/ws/stream")
async def websocket_webcam(websocket: WebSocket):
    await handle_webcam_stream(websocket)


@app.websocket("/ws/rtsp")
async def websocket_rtsp(websocket: WebSocket, url: str = Query(...)):
    await handle_rtsp_stream(websocket, url)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=False)
