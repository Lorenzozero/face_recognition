"""
conftest.py — fixture condivise per i test di face_recognition-ng
"""
import io
import json
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture(scope="module")
def client():
    """TestClient FastAPI con mock dei moduli pesanti (InsightFace, DB, OSINT)."""
    with patch("face_recognition.face_locations", return_value=[(10, 90, 90, 10)]), \
         patch("face_recognition.face_encodings", return_value=[np.random.rand(512)]), \
         patch("face_recognition.face_distance", return_value=np.array([0.3])), \
         patch("face_recognition.compare_faces", return_value=[True]):
        from api_server import app
        yield TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token-ci"}


@pytest.fixture
def sample_image_bytes():
    """Immagine JPEG 100x100 sintetica (viso fittizio)."""
    img = Image.fromarray(
        np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    )
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.getvalue()
