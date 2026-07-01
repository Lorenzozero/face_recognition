"""
vision_engine.py — InsightFace + Supervision engine
Sostituisce dlib HOG per detection ed embedding.
Compatibile con face_db.py esistente (embeddings 512D).

Usage:
    from vision_engine import VisionEngine
    engine = VisionEngine()  # ctx_id=0 per GPU, -1 per CPU
    detections, embeddings = engine.process_frame(frame_bgr)
"""

from __future__ import annotations

import numpy as np
from typing import List, Tuple, Optional

try:
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False

try:
    import supervision as sv
    SUPERVISION_AVAILABLE = True
except ImportError:
    SUPERVISION_AVAILABLE = False

# Fallback a face_recognition se InsightFace non disponibile
try:
    import face_recognition as _fr_legacy
    LEGACY_AVAILABLE = True
except ImportError:
    LEGACY_AVAILABLE = False


class VisionEngine:
    """
    Engine unificato per detection + embedding.
    Usa InsightFace se disponibile, altrimenti fallback a dlib.
    """

    def __init__(self, ctx_id: int = -1, det_thresh: float = 0.5):
        """
        ctx_id: -1 = CPU, 0 = prima GPU CUDA
        det_thresh: soglia confidence detection (0.0-1.0)
        """
        self.use_insightface = INSIGHTFACE_AVAILABLE
        self.use_supervision = SUPERVISION_AVAILABLE
        self.det_thresh = det_thresh
        self._tracker = None
        self._zone = None

        if self.use_insightface:
            self._app = FaceAnalysis(
                name="buffalo_l",
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"] if ctx_id >= 0
                          else ["CPUExecutionProvider"],
            )
            self._app.prepare(ctx_id=ctx_id, det_thresh=det_thresh)
            print(f"[VisionEngine] InsightFace buffalo_l caricato (ctx_id={ctx_id})")
        elif LEGACY_AVAILABLE:
            print("[VisionEngine] InsightFace non disponibile, fallback a dlib face_recognition")
        else:
            raise RuntimeError("Nessun backend CV disponibile. Installa insightface o face_recognition.")

        if self.use_supervision:
            self._tracker = sv.ByteTrack()
            print("[VisionEngine] Supervision ByteTrack inizializzato")

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def process_frame(
        self,
        frame_bgr: np.ndarray,
        track: bool = False,
    ) -> Tuple[Optional[object], List[np.ndarray]]:
        """
        Processa un frame BGR (OpenCV) o RGB.
        Ritorna (sv.Detections | None, lista embeddings 512D).
        """
        if self.use_insightface:
            return self._process_insightface(frame_bgr, track=track)
        else:
            return self._process_legacy(frame_bgr)

    def embed_image(self, img_rgb: np.ndarray) -> List[np.ndarray]:
        """
        Estrae embeddings 512D da un'immagine RGB.
        Compatibile drop-in con face_recognition.face_encodings().
        """
        _, embeddings = self.process_frame(img_rgb)
        return embeddings

    # ------------------------------------------------------------------
    # InsightFace backend
    # ------------------------------------------------------------------

    def _process_insightface(
        self,
        frame: np.ndarray,
        track: bool = False,
    ) -> Tuple[Optional[object], List[np.ndarray]]:
        faces = self._app.get(frame)
        if not faces:
            if self.use_supervision:
                return sv.Detections.empty(), []
            return None, []

        xyxy = np.array([f.bbox for f in faces], dtype=np.float32)
        confidence = np.array([f.det_score for f in faces], dtype=np.float32)
        embeddings = [f.embedding for f in faces]

        if self.use_supervision:
            detections = sv.Detections(xyxy=xyxy, confidence=confidence)
            if track and self._tracker is not None:
                detections = self._tracker.update_with_detections(detections)
            return detections, embeddings

        return xyxy, embeddings

    # ------------------------------------------------------------------
    # Legacy dlib fallback
    # ------------------------------------------------------------------

    def _process_legacy(
        self,
        img_rgb: np.ndarray,
    ) -> Tuple[Optional[object], List[np.ndarray]]:
        try:
            locations = _fr_legacy.face_locations(img_rgb)
            encodings = _fr_legacy.face_encodings(img_rgb, locations)
        except Exception:
            return None, []

        if not locations:
            return None, []

        # Converti (top, right, bottom, left) -> xyxy
        xyxy = np.array(
            [[left, top, right, bottom] for top, right, bottom, left in locations],
            dtype=np.float32,
        )

        if self.use_supervision:
            detections = sv.Detections(xyxy=xyxy)
            return detections, encodings

        return xyxy, encodings

    # ------------------------------------------------------------------
    # Zone OSINT trigger
    # ------------------------------------------------------------------

    def set_trigger_zone(
        self,
        polygon: List[Tuple[int, int]],
        frame_resolution: Tuple[int, int],
    ) -> None:
        """
        Definisce una PolygonZone. Un volto dentro la zona trigghera OSINT.
        polygon: lista di (x, y) in pixel
        frame_resolution: (width, height)
        """
        if not self.use_supervision:
            print("[VisionEngine] Supervision non disponibile, zone ignorate")
            return
        self._zone = sv.PolygonZone(
            polygon=np.array(polygon),
            frame_resolution_wh=frame_resolution,
        )

    def faces_in_zone(self, detections) -> bool:
        """Ritorna True se almeno un volto è dentro la trigger zone."""
        if self._zone is None or detections is None:
            return False
        try:
            mask = self._zone.trigger(detections=detections)
            return bool(mask.any())
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Annotazione video (supervision)
    # ------------------------------------------------------------------

    def annotate_frame(
        self,
        frame: np.ndarray,
        detections,
        labels: Optional[List[str]] = None,
    ) -> np.ndarray:
        """
        Disegna bounding box + label sul frame.
        Ritorna il frame annotato.
        """
        if not self.use_supervision or detections is None:
            return frame
        box_ann = sv.BoxAnnotator()
        frame = box_ann.annotate(scene=frame.copy(), detections=detections)
        if labels:
            label_ann = sv.LabelAnnotator()
            frame = label_ann.annotate(
                scene=frame,
                detections=detections,
                labels=labels,
            )
        return frame
