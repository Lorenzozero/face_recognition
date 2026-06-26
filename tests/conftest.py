"""
conftest.py — fixture condivise per i test di face_recognition-ng

Strategia di mock:
  1. face_recognition viene iniettato in sys.modules come MagicMock PRIMA
     che api_server venga importato, cosi intercetta anche l'import top-level.
  2. onnxruntime viene stubbato se assente (non installato in CI).
  3. api_server.db viene sostituito con MagicMock per evitare accessi SQLite.
  4. Le fixture usano scope='session': app e client vengono creati una volta sola.
"""
import io
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

# --- stub face_recognition in sys.modules prima di qualsiasi import ---
_fr_stub = MagicMock()
_fr_stub.face_locations.return_value = [(10, 90, 90, 10)]
_fr_stub.face_encodings.return_value = [np.zeros(512, dtype=np.float32)]
_fr_stub.face_distance.return_value  = np.array([0.0])
_fr_stub.compare_faces.return_value  = [True]
sys.modules.setdefault("face_recognition", _fr_stub)

# --- stub onnxruntime se non installato ---
if "onnxruntime" not in sys.modules:
    sys.modules["onnxruntime"] = MagicMock()


@pytest.fixture(scope="session")
def app():
    """Crea l'app FastAPI una sola volta per sessione."""
    db_mock = MagicMock(
        list_known=MagicMock(return_value=[]),
        register=MagicMock(return_value=1),
        delete=MagicMock(return_value=None),
    )
    import api_server
    api_server.db = db_mock
    return api_server.app


@pytest.fixture(scope="session")
def client(app):
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token-ci"}


@pytest.fixture
def sample_image_bytes():
    img = Image.fromarray(
        np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    )
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.getvalue()
