"""
test_api_osint.py — Test endpoint OSINT: /osint/image, /osint/social, /osint/full
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


MOCK_REVERSE = {
    "image_hash": "abc123",
    "timestamp": 1700000000,
    "total_results": 1,
    "sources": {
        "google_lens": {"results": [{"url": "https://lens.google.com/test", "title": "Google Lens", "source": "google_lens"}]},
        "yandex":      {"results": []},
        "tineye":      {"results": []},
        "search_links":{"results": []},
    },
}
MOCK_SOCIAL  = {"platforms": [{"platform": "Instagram", "found": False, "url": ""}]}
MOCK_LINKS   = {"google_dork": "site:instagram.com Mario Rossi"}
MOCK_VARIANTS= ["mariorossi", "mario.rossi", "mario_rossi"]


def test_osint_image_no_auth(client, sample_image_bytes):
    r = client.post(
        "/osint/image",
        files={"file": ("t.jpg", sample_image_bytes, "image/jpeg")},
    )
    assert r.status_code == 401


def test_osint_image_with_auth(client, auth_headers, sample_image_bytes):
    with patch("api_server.osint.search", new=AsyncMock(return_value=MOCK_REVERSE)):
        r = client.post(
            "/osint/image",
            headers=auth_headers,
            files={"file": ("t.jpg", sample_image_bytes, "image/jpeg")},
        )
    assert r.status_code == 200
    data = r.json()
    assert "faces_detected" in data
    assert "face_cropped" in data
    assert "sources" in data


def test_osint_social_by_name(client, auth_headers):
    with patch("api_server.social.search_by_name",             new=AsyncMock(return_value=MOCK_SOCIAL)), \
         patch("api_server.social.generate_osint_report_links", return_value=MOCK_LINKS), \
         patch("api_server.maigret.generate_username_variants",  return_value=MOCK_VARIANTS):
        r = client.post(
            "/osint/social",
            headers=auth_headers,
            json={"name": "Mario Rossi", "run_maigret": False},
        )
    assert r.status_code == 200
    data = r.json()
    assert "by_name" in data
    assert "username_variants" in data


def test_osint_full_pipeline(client, auth_headers, sample_image_bytes):
    with patch("api_server.osint.search",                       new=AsyncMock(return_value=MOCK_REVERSE)), \
         patch("api_server.social.search_by_name",              new=AsyncMock(return_value=MOCK_SOCIAL)), \
         patch("api_server.social.generate_osint_report_links",  return_value=MOCK_LINKS), \
         patch("api_server.maigret.generate_username_variants",   return_value=MOCK_VARIANTS):
        r = client.post(
            "/osint/full",
            headers=auth_headers,
            files={"file": ("t.jpg", sample_image_bytes, "image/jpeg")},
            data={"name": "Mario Rossi", "run_maigret": "false"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["target_name"] == "Mario Rossi"
    assert "reverse_image" in data
    assert "social" in data
    assert "username_variants" in data
    assert data["faces_detected"] == 1
