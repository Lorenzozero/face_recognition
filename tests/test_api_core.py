"""
test_api_core.py — Test degli endpoint core dell'API REST.
"""
import io
import numpy as np
import pytest
from unittest.mock import patch


def test_health(client):
    """GET /health deve restituire 200 e versione."""
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_encode_no_auth(client, sample_image_bytes):
    """POST /encode senza token deve restituire 401."""
    r = client.post("/encode", files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")})
    assert r.status_code == 401


def test_encode_with_auth(client, auth_headers, sample_image_bytes):
    """POST /encode con token deve restituire encoding validi."""
    r = client.post(
        "/encode",
        headers=auth_headers,
        files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
    )
    assert r.status_code == 200
    data = r.json()
    assert "faces_found" in data
    assert "encodings" in data
    assert "locations" in data


def test_detect_with_auth(client, auth_headers, sample_image_bytes):
    """POST /detect deve restituire le location dei volti."""
    r = client.post(
        "/detect",
        headers=auth_headers,
        files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
    )
    assert r.status_code == 200
    data = r.json()
    assert "faces_found" in data
    assert "locations" in data
    assert isinstance(data["locations"], list)


def test_compare_match(client, auth_headers):
    """POST /compare con encoding identici deve dare match=True e distance=0."""
    enc = np.random.rand(512).tolist()
    r = client.post(
        "/compare",
        headers=auth_headers,
        json={"encoding_a": enc, "encoding_b": enc, "tolerance": 0.6},
    )
    assert r.status_code == 200
    data = r.json()
    assert "match" in data
    assert "distance" in data
    assert data["distance"] == pytest.approx(0.0, abs=1e-4)
    assert data["match"] is True


def test_compare_no_match(client, auth_headers):
    """POST /compare con encoding diversi e tolerance bassa deve dare match=False."""
    enc_a = [1.0] * 512
    enc_b = [0.0] * 512
    r = client.post(
        "/compare",
        headers=auth_headers,
        json={"encoding_a": enc_a, "encoding_b": enc_b, "tolerance": 0.1},
    )
    assert r.status_code == 200
    assert r.json()["match"] is False


def test_known_list_empty(client, auth_headers):
    """GET /known deve restituire una lista (anche vuota)."""
    with patch("api_server.db.list_known", return_value=[]):
        r = client.get("/known", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_delete_known(client, auth_headers):
    """DELETE /known/{id} deve restituire 200."""
    with patch("api_server.db.delete", return_value=None):
        r = client.delete("/known/1", headers=auth_headers)
    assert r.status_code == 200
    assert "eliminato" in r.json()["message"]
