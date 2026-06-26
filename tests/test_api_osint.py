"""
test_api_osint.py — Test degli endpoint OSINT.
"""
import io
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def test_osint_image_no_auth(client, sample_image_bytes):
    """POST /osint/image senza token deve restituire 401."""
    r = client.post(
        "/osint/image",
        files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
    )
    assert r.status_code == 401


def test_osint_image_with_auth(client, auth_headers, sample_image_bytes):
    """POST /osint/image con token deve chiamare il motore OSINT."""
    mock_result = {
        "google_lens": "https://lens.google.com/uploadbyurl?url=test",
        "yandex": "https://yandex.com/images/search?url=test",
        "tineye": "https://tineye.com/search?url=test",
    }
    with patch("api_server.osint.search", new=AsyncMock(return_value=mock_result)):
        r = client.post(
            "/osint/image",
            headers=auth_headers,
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
        )
    assert r.status_code == 200
    data = r.json()
    assert "faces_detected" in data
    assert "face_cropped" in data


def test_osint_social_by_name(client, auth_headers):
    """POST /osint/social con nome deve restituire varianti e link."""
    mock_social = {"platforms": [{"platform": "Instagram", "found": False, "url": ""}]}
    mock_links = {"google_dork": "site:instagram.com Mario Rossi"}
    mock_variants = ["mariorossi", "mario.rossi", "mario_rossi"]

    with patch("api_server.social.search_by_name", new=AsyncMock(return_value=mock_social)), \
         patch("api_server.social.generate_osint_report_links", return_value=mock_links), \
         patch("api_server.maigret.generate_username_variants", return_value=mock_variants):
        r = client.post(
            "/osint/social",
            headers=auth_headers,
            json={"name": "Mario Rossi", "run_maigret": False},
        )
    assert r.status_code == 200
    data = r.json()
    assert "by_name" in data or "username_variants" in data


def test_osint_full_pipeline(client, auth_headers, sample_image_bytes):
    """POST /osint/full deve restituire tutti i campi della pipeline."""
    mock_reverse = {"google_lens": "https://lens.google.com/test"}
    mock_social  = {"platforms": []}
    mock_links   = {}
    mock_variants= ["mariorossi"]

    with patch("api_server.osint.search",  new=AsyncMock(return_value=mock_reverse)), \
         patch("api_server.social.search_by_name", new=AsyncMock(return_value=mock_social)), \
         patch("api_server.social.generate_osint_report_links", return_value=mock_links), \
         patch("api_server.maigret.generate_username_variants", return_value=mock_variants):
        r = client.post(
            "/osint/full",
            headers=auth_headers,
            files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
            data={"name": "Mario Rossi", "run_maigret": "false"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["target_name"] == "Mario Rossi"
    assert "reverse_image" in data
    assert "social" in data
    assert "username_variants" in data
