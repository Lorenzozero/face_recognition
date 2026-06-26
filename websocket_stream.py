"""
face_recognition-ng — WebSocket Video Stream Handler
Gestisce flussi video in tempo reale da:
  - Webcam browser (frame JPEG via WebSocket)
  - IP camera / stream RTSP tramite OpenCV lato server

Usage:
    Avviare tramite api_server.py (integrato automaticamente)
    Stream RTSP: ws://localhost:8000/ws/rtsp?url=rtsp://...
"""

import asyncio
import base64
import json
import cv2
import numpy as np
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
import face_recognition
from face_db import FaceDatabase

db = FaceDatabase()


async def handle_webcam_stream(websocket: WebSocket):
    """
    Gestisce stream webcam dal browser.
    Il browser invia frame JPEG in base64, il server risponde con
    le bounding box e i nomi dei volti riconosciuti.
    """
    await websocket.accept()
    print("[WebSocket] Client webcam connesso")
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            # Decodifica frame JPEG base64
            img_data = base64.b64decode(payload["frame"].split(",")[1])
            nparr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Rilevamento e riconoscimento
            locations = face_recognition.face_locations(frame_rgb)
            encodings = face_recognition.face_encodings(frame_rgb)

            results = []
            for loc, enc in zip(locations, encodings):
                top, right, bottom, left = loc
                match = db.find_match(enc)
                results.append({
                    "top": top, "right": right,
                    "bottom": bottom, "left": left,
                    "name": match["name"] if match else "Sconosciuto",
                    "confidence": round(1 - match["distance"], 3) if match else 0.0,
                    "matched": match is not None,
                })

            await websocket.send_text(json.dumps({
                "faces": results,
                "faces_count": len(results),
            }))

    except WebSocketDisconnect:
        print("[WebSocket] Client webcam disconnesso")


async def handle_rtsp_stream(websocket: WebSocket, rtsp_url: str):
    """
    Legge uno stream RTSP/IP camera tramite OpenCV lato server
    e invia i risultati di riconoscimento al browser via WebSocket.
    """
    await websocket.accept()
    print(f"[RTSP] Connessione a: {rtsp_url}")

    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        await websocket.send_text(json.dumps({"error": f"Impossibile aprire stream: {rtsp_url}"}))
        await websocket.close()
        return

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                await websocket.send_text(json.dumps({"error": "Stream interrotto"}))
                break

            # Ridimensiona per velocizzare l'analisi
            small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
            rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            locations = face_recognition.face_locations(rgb_frame)
            encodings = face_recognition.face_encodings(rgb_frame)

            results = []
            for loc, enc in zip(locations, encodings):
                top, right, bottom, left = loc
                # Riscala le coordinate al frame originale
                top *= 2; right *= 2; bottom *= 2; left *= 2
                match = db.find_match(enc)
                results.append({
                    "top": top, "right": right,
                    "bottom": bottom, "left": left,
                    "name": match["name"] if match else "Sconosciuto",
                    "confidence": round(1 - match["distance"], 3) if match else 0.0,
                    "matched": match is not None,
                })

            # Invia frame JPEG + risultati
            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
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
