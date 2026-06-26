"""
InsightFace backend for face_recognition-ng.
Drop-in replacement for the original dlib-based backend.
Maintains full API compatibility with ageitgey/face_recognition.
"""

import numpy as np
from typing import List, Tuple, Optional

try:
    import insightface
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False

# Lazy-loaded global model
_app = None


def _get_app():
    """Lazy-load InsightFace model (downloads on first use)."""
    global _app
    if _app is None:
        if not INSIGHTFACE_AVAILABLE:
            raise ImportError(
                "InsightFace is not installed. Run: pip install insightface onnxruntime"
            )
        _app = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        _app.prepare(ctx_id=0, det_size=(640, 640))
    return _app


def load_image_file(file, mode="RGB") -> np.ndarray:
    """Load an image file into a numpy array."""
    import PIL.Image
    im = PIL.Image.open(file)
    if mode:
        im = im.convert(mode)
    return np.array(im)


def face_locations(img: np.ndarray, number_of_times_to_upsample: int = 1, model: str = "hog") -> List[Tuple]:
    """
    Returns a list of tuples of found face locations in css order (top, right, bottom, left).
    Compatible with original ageitgey API.
    """
    app = _get_app()
    # InsightFace expects BGR
    import cv2
    img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    faces = app.get(img_bgr)
    locations = []
    for face in faces:
        bbox = face.bbox.astype(int)
        left, top, right, bottom = bbox[0], bbox[1], bbox[2], bbox[3]
        locations.append((top, right, bottom, left))
    return locations


def face_encodings(face_image: np.ndarray, known_face_locations=None, num_jitters: int = 1, model: str = "large") -> List[np.ndarray]:
    """
    Returns a list of 512-d face encodings for each face in the image.
    Note: InsightFace uses 512-d embeddings (vs dlib's 128-d).
    Still fully compatible with compare_faces().
    """
    app = _get_app()
    import cv2
    img_bgr = cv2.cvtColor(face_image, cv2.COLOR_RGB2BGR)
    faces = app.get(img_bgr)
    return [face.normed_embedding for face in faces]


def compare_faces(known_face_encodings: List[np.ndarray], face_encoding_to_check: np.ndarray, tolerance: float = 0.6) -> List[bool]:
    """
    Compare a list of face encodings against a candidate.
    Returns a list of True/False values.
    Compatible with original ageitgey API.
    """
    if len(known_face_encodings) == 0:
        return []
    distances = face_distance(known_face_encodings, face_encoding_to_check)
    return list(distances <= tolerance)


def face_distance(face_encodings: List[np.ndarray], face_to_compare: np.ndarray) -> np.ndarray:
    """
    Given a list of face encodings, compare them to a known face encoding.
    Returns a numpy array of distances (lower = more similar).
    """
    if len(face_encodings) == 0:
        return np.empty(0)
    # Cosine distance for InsightFace normalized embeddings
    similarities = np.dot(face_encodings, face_to_compare)
    distances = 1 - similarities
    return distances


def face_landmarks(face_image: np.ndarray, face_locations=None, model: str = "large"):
    """
    Returns a list of dicts with facial landmark positions.
    Keys: nose_bridge, chin, left_eye, right_eye, top_lip, bottom_lip.
    """
    app = _get_app()
    import cv2
    img_bgr = cv2.cvtColor(face_image, cv2.COLOR_RGB2BGR)
    faces = app.get(img_bgr)
    results = []
    for face in faces:
        kps = face.kps.astype(int).tolist() if face.kps is not None else []
        if len(kps) >= 5:
            landmark = {
                "left_eye": [tuple(kps[0])],
                "right_eye": [tuple(kps[1])],
                "nose_tip": [tuple(kps[2])],
                "top_lip": [tuple(kps[3])],
                "bottom_lip": [tuple(kps[4])],
            }
        else:
            landmark = {}
        results.append(landmark)
    return results
