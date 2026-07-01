"""
face_recognition-ng — WebSocket Video Stream Handler v2.0
Gestisce flussi video in tempo reale da:
  - Webcam browser (frame JPEG via WebSocket)
  - IP camera / stream RTSP tramite OpenCV lato server

Usa VisionEngine (InsightFace + Supervision) per detection,
tracking ByteTrack e annotazione frame.
"""

import asyncio
import base64
import json
import cv2
import numpy as np
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
from face_db import FaceDatabase
from vision_engine import VisionEngine

db = FaceDatabase()


async def handle_webcam_stream(websocket: WebSocket, vision: Optional[VisionEngine] = None):
    """
    Gestisce stream webcam dal browser.
    Il browser invia frame JPEG in base64; il server risponde con
    bounding box, nomi, track_id e frame annotato.
    """
    if vision is None:
        vision = VisionEngine(ctx_id=-1)

    await websocket.accept()
    print("[WebSocket] Client webcam connesso")

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            # Decodifica frame JPEG base64
            img_data = base64.b64decode(payload["frame"].split(",")[1])
            nparr = np.frombuffer(img_data, np.uint8)
            frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

            # Detection + tracking
            detections, embeddings = vision.process_frame(frame_rgb, track=True)

            results = []
            labels = []

            for i, emb in enumerate(embeddings):
                match = db.find_match(emb)
                name = match["name"] if match else "Sconosciuto"
                confidence = round(1 - match["distance"], 3) if match else 0.0
                track_id = None
                try:
                    if detections is not None and detections.tracker_id is not None and i < len(detections.tracker_id):
                        track_id = int(detections.tracker_id[i])
                    x1, y1, x2, y2 = detections.xyxy[i].astype(int)
                    top, right, bottom, left = int(y1), int(x2), int(y2), int(x1)
                except Exception:
                    top = right = bottom = left = 0

                results.append({
                    "top": top, "right": right,
                    "bottom": bottom, "left": left,
                    "name": name,
                    "confidence": confidence,
                    "matched": match is not None,
                    "track_id": track_id,
                })
                labels.append(f"{name} ({confidence:.2f})")

            # Frame annotato con bbox + label
            annotated = vision.annotate_frame(frame_bgr, detections, labels)
            _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            frame_b64 = base64.b64encode(jpeg.tobytes()).decode()

            await websocket.send_text(json.dumps({
                "frame": f"data:image/jpeg;base64,{frame_b64}",
                "faces": results,
                "faces_count": len(results),
            }))

    except WebSocketDisconnect:
        print("[WebSocket] Client webcam disconnesso")


async def handle_rtsp_stream(websocket: WebSocket, rtsp_url: str, vision: Optional[VisionEngine] = None):
    """
    Legge stream RTSP/IP camera via OpenCV e invia risultati al browser.
    """
    if vision is None:
        vision = VisionEngine(ctx_id=-1)

    await websocket.accept()
    print(f"[RTSP] Connessione a: {rtsp_url}")

    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        await websocket.send_text(json.dumps({"error": f"Impossibile aprire stream: {rtsp_url}"}))
        await websocket.close()
        return

    try:
        while True:
            ret, frame_bgr = cap.read()
            if not ret:
                await websocket.send_text(json.dumps({"error": "Stream interrotto"}))
                break

            # Ridimensiona per velocizzare l'analisi
            small = cv2.resize(frame_bgr, (0, 0), fx=0.5, fy=0.5)
            small_rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

            detections, embeddings = vision.process_frame(small_rgb, track=True)

            results = []
            labels = []

            for i, emb in enumerate(embeddings):
                match = db.find_match(emb)
                name = match["name"] if match else "Sconosciuto"
                confidence = round(1 - match["distance"], 3) if match else 0.0
                track_id = None
                try:
                    if detections is not None and detections.tracker_id is not None and i < len(detections.tracker_id):
                        track_id = int(detections.tracker_id[i])
                    x1, y1, x2, y2 = (detections.xyxy[i] * 2).astype(int)  # riscala al frame originale
                    top, right, bottom, left = int(y1), int(x2), int(y2), int(x1)
                except Exception:
                    top = right = bottom = left = 0

                results.append({
                    "top": top, "right": right,
                    "bottom": bottom, "left": left,
                    "name": name,
                    "confidence": confidence,
                    "matched": match is not None,
                    "track_id": track_id,
                })
                labels.append(f"{name} ({confidence:.2f})")

            # Annota frame originale (non ridimensionato)
            if detections is not None:
                try:
                    import supervision as sv
                    det_full = sv.Detections(xyxy=detections.xyxy * 2)
                    if detections.tracker_id is not None:
                        det_full.tracker_id = detections.tracker_id
                    annotated = vision.annotate_frame(frame_bgr, det_full, labels)
                except Exception:
                    annotated = frame_bgr
            else:
                annotated = frame_bgr

            _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 60])
            frame_b64 = base64.b64encode(jpeg.tobytes()).decode()

            await websocket.send_text(json.dumps({
                "frame": f"data:image/jpeg;base64,{frame_b64}",
                "faces": results,
                "faces_count": len(results),
            }))

            await asyncio.sleep(0.05)  # ~20 FPS max

    except WebSocketDisconnect:
        print("[RTSP] Client disconnesso")
    finally:
        cap.release()
