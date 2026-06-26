"""
test_report_pdf.py — Test generatore PDF (unit) + endpoint /report/pdf (integration)
"""
import io
import pytest
import numpy as np
from unittest.mock import AsyncMock, patch
from PIL import Image


# ── helpers ───────────────────────────────────────────────────────────────────────

MOCK_REVERSE  = {
    "image_hash": "abc123", "timestamp": 1700000000, "total_results": 1,
    "sources": {
        "google_lens": {"results": [{"url": "https://lens.google.com/test", "title": "Google Lens", "source": "google_lens"}]},
        "yandex":      {"results": []},
        "tineye":      {"results": []},
        "search_links":{"results": []},
    },
}
MOCK_SOCIAL   = {"platforms": [
    {"platform": "Instagram", "found": True,  "url": "https://instagram.com/test"},
    {"platform": "Twitter",   "found": False, "url": ""},
    {"platform": "GitHub",    "found": True,  "url": "https://github.com/test"},
]}
MOCK_LINKS    = {"google_dork": "site:instagram.com Test Target"}
MOCK_VARIANTS = ["testtarget", "test.target", "t.target"]


def _osint_data(name="Test Target", maigret=None):
    return {
        "target_name": name,
        "faces_detected": 1,
        "reverse_image": MOCK_REVERSE,
        "social": MOCK_SOCIAL,
        "osint_links": MOCK_LINKS,
        "username_variants": MOCK_VARIANTS,
        "maigret": maigret,
    }


# ── Unit: build_pdf ───────────────────────────────────────────────────────────────

def test_build_pdf_returns_bytes():
    from report_generator import build_pdf
    result = build_pdf(_osint_data())
    assert isinstance(result, bytes)
    assert len(result) > 1024
    assert result[:4] == b"%PDF"


def test_build_pdf_with_image():
    from report_generator import build_pdf
    img = Image.fromarray(np.random.randint(0, 255, (60, 60, 3), dtype=np.uint8))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    result = build_pdf(_osint_data(), target_image_bytes=buf.getvalue())
    assert result[:4] == b"%PDF"
    assert len(result) > 2048


def test_build_pdf_no_maigret():
    from report_generator import build_pdf
    result = build_pdf(_osint_data(maigret=None))
    assert result[:4] == b"%PDF"


def test_build_pdf_with_maigret():
    from report_generator import build_pdf
    maigret = {
        "testtarget": {"sites": [
            {"site": "GitHub",    "url": "https://github.com/testtarget",    "status": "found"},
            {"site": "Twitter",   "url": "https://twitter.com/testtarget",   "status": "found"},
            {"site": "Instagram", "url": "https://instagram.com/testtarget", "status": 404},
        ]}
    }
    result = build_pdf(_osint_data(maigret=maigret))
    assert result[:4] == b"%PDF"


# ── Integration: /report/pdf ───────────────────────────────────────────────────────

def test_report_pdf_endpoint_no_auth(client, sample_image_bytes):
    r = client.post(
        "/report/pdf",
        files={"file": ("t.jpg", sample_image_bytes, "image/jpeg")},
        data={"name": "Mario Rossi"},
    )
    assert r.status_code == 401


def test_report_pdf_endpoint_ok(client, auth_headers, sample_image_bytes):
    with patch("api_server.osint.search",                       new=AsyncMock(return_value=MOCK_REVERSE)), \
         patch("api_server.social.search_by_name",              new=AsyncMock(return_value=MOCK_SOCIAL)), \
         patch("api_server.social.generate_osint_report_links",  return_value=MOCK_LINKS), \
         patch("api_server.maigret.generate_username_variants",   return_value=MOCK_VARIANTS):
        r = client.post(
            "/report/pdf",
            headers=auth_headers,
            files={"file": ("t.jpg", sample_image_bytes, "image/jpeg")},
            data={"name": "Mario Rossi", "run_maigret": "false"},
        )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1024
    assert "osint_report_mario_rossi.pdf" in r.headers.get("content-disposition", "")
