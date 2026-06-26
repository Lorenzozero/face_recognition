"""
test_report_pdf.py — Test del generatore PDF e dell'endpoint /report/pdf.
"""
import io
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from PIL import Image
import numpy as np


# ─ Unit test: build_pdf restituisce bytes validi ──────────────────────────────────

def _minimal_osint_data(name="Test Target"):
    return {
        "target_name": name,
        "faces_detected": 1,
        "reverse_image": {
            "google_lens": "https://lens.google.com/test",
            "yandex": "https://yandex.com/test",
        },
        "social": {
            "platforms": [
                {"platform": "Instagram", "found": True,  "url": "https://instagram.com/test"},
                {"platform": "Twitter",   "found": False, "url": ""},
                {"platform": "GitHub",    "found": True,  "url": "https://github.com/test"},
            ]
        },
        "osint_links": {"google_dork": "site:instagram.com Test Target"},
        "username_variants": ["testtarget", "test.target", "t.target"],
        "maigret": None,
    }


def test_build_pdf_returns_bytes():
    """build_pdf deve restituire bytes non vuoti che iniziano con %PDF."""
    from report_generator import build_pdf
    data = _minimal_osint_data()
    result = build_pdf(data)
    assert isinstance(result, bytes)
    assert len(result) > 1024  # almeno 1 KB
    assert result[:4] == b"%PDF"  # magic bytes PDF validi


def test_build_pdf_with_image():
    """build_pdf con immagine target deve includere la foto nel PDF."""
    from report_generator import build_pdf
    img = Image.fromarray(np.random.randint(0, 255, (60, 60, 3), dtype=np.uint8))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    result = build_pdf(_minimal_osint_data(), target_image_bytes=img_bytes)
    assert result[:4] == b"%PDF"
    assert len(result) > 2048


def test_build_pdf_empty_maigret():
    """build_pdf con maigret=None non deve sollevare eccezioni."""
    from report_generator import build_pdf
    data = _minimal_osint_data()
    data["maigret"] = None
    result = build_pdf(data)
    assert result[:4] == b"%PDF"


def test_build_pdf_with_maigret_results():
    """build_pdf con risultati Maigret deve includere la tabella siti."""
    from report_generator import build_pdf
    data = _minimal_osint_data()
    data["maigret"] = {
        "testtarget": {
            "sites": [
                {"site": "GitHub",    "url": "https://github.com/testtarget",    "status": "found"},
                {"site": "Twitter",   "url": "https://twitter.com/testtarget",   "status": "found"},
                {"site": "Instagram", "url": "https://instagram.com/testtarget", "status": 404},
            ]
        }
    }
    result = build_pdf(data)
    assert result[:4] == b"%PDF"


# ─ Integration test: endpoint /report/pdf ─────────────────────────────────────

def test_report_pdf_endpoint_no_auth(client, sample_image_bytes):
    """POST /report/pdf senza token deve restituire 401."""
    r = client.post(
        "/report/pdf",
        files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
        data={"name": "Mario Rossi"},
    )
    assert r.status_code == 401


def test_report_pdf_endpoint_returns_pdf(client, auth_headers, sample_image_bytes):
    """POST /report/pdf deve restituire un PDF valido con Content-Type corretto."""
    mock_reverse  = {"google_lens": "https://lens.google.com/test"}
    mock_social   = {"platforms": [{"platform": "Instagram", "found": False, "url": ""}]}
    mock_links    = {}
    mock_variants = ["mariorossi", "mario.rossi"]

    with patch("api_server.osint.search",  new=AsyncMock(return_value=mock_reverse)), \
         patch("api_server.social.search_by_name", new=AsyncMock(return_value=mock_social)), \
         patch("api_server.social.generate_osint_report_links", return_value=mock_links), \
         patch("api_server.maigret.generate_username_variants", return_value=mock_variants):
        r = client.post(
            "/report/pdf",
            headers=auth_headers,
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            data={"name": "Mario Rossi", "run_maigret": "false"},
        )

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1024
    assert "osint_report_mario_rossi.pdf" in r.headers.get("content-disposition", "")
