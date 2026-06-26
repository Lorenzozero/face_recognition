"""
conftest.py — fixture condivise per i test di face_recognition-ng
"""
import io
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture(scope="module")
def client():
    """
    TestClient FastAPI.
    I mock sono applicati su api_server.face_recognition.* (dove vengono chiamati),
    non sul modulo originale, così intercettano correttamente le route.
    """
    mock_locations = [(10, 90, 90, 10)]
    mock_encoding  = np.zeros(512, dtype=np.float32)  # encoding fisso zero

    with patch("api_server.face_recognition.face_locations", return_value=mock_locations), \
         patch("api_server.face_recognition.face_encodings",  return_value=[mock_encoding]), \
         patch("api_server.face_recognition.face_distance",   return_value=np.array([0.0])), \
         patch("api_server.face_recognition.compare_faces",   return_value=[True]), \
         patch("api_server.db", MagicMock(
             list_known=MagicMock(return_value=[]),
             register=MagicMock(return_value=1),
             delete=MagicMock(return_value=None),
         )):
        from api_server import app
        yield TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token-ci"}


@pytest.fixture
def sample_image_bytes():
    """Immagine JPEG 100x100 sintetica."""
    img = Image.fromarray(
        np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    )
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.getvalue()
