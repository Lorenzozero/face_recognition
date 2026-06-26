"""
test_api_core.py — Test endpoint core: /health, /encode, /detect, /compare, /known, /known/{id}
"""
import numpy as np
import pytest
from unittest.mock import MagicMock, patch


# ── /health ──────────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


# ── /encode ───────────────────────────────────────────────────────────────────────

def test_encode_no_auth(client, sample_image_bytes):
    r = client.post("/encode", files={"file": ("t.jpg", sample_image_bytes, "image/jpeg")})
    assert r.status_code == 401


def test_encode_with_auth(client, auth_headers, sample_image_bytes):
    r = client.post(
        "/encode",
        headers=auth_headers,
        files={"file": ("t.jpg", sample_image_bytes, "image/jpeg")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["faces_found"] == 1
    assert len(data["encodings"]) == 1
    assert len(data["encodings"][0]) == 512
    assert len(data["locations"]) == 1


# ── /detect ───────────────────────────────────────────────────────────────────────

def test_detect_with_auth(client, auth_headers, sample_image_bytes):
    r = client.post(
        "/detect",
        headers=auth_headers,
        files={"file": ("t.jpg", sample_image_bytes, "image/jpeg")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["faces_found"] == 1
    assert data["locations"] == [[10, 90, 90, 10]]


# ── /compare ─────────────────────────────────────────────────────────────────────

def test_compare_match(client, auth_headers):
    """/compare con encoding identici: distance=0.0, match=True (mock restituisce 0.0)."""
    enc = [0.0] * 512
    r = client.post(
        "/compare",
        headers=auth_headers,
        json={"encoding_a": enc, "encoding_b": enc, "tolerance": 0.6},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["match"] is True
    assert data["distance"] == pytest.approx(0.0, abs=1e-4)


def test_compare_no_match(client, auth_headers):
    """/compare con tolerance 0.0 e distance 0.0 (dal mock): match dipende da tolerance."""
    enc_a = [0.0] * 512
    enc_b = [0.0] * 512
    # tolerance -0.1 (impossibile) → match=False anche con distance=0
    r = client.post(
        "/compare",
        headers=auth_headers,
        json={"encoding_a": enc_a, "encoding_b": enc_b, "tolerance": -0.1},
    )
    assert r.status_code == 200
    assert r.json()["match"] is False


# ── /known e /known/{id} ───────────────────────────────────────────────────────

def test_known_list_empty(client, auth_headers):
    r = client.get("/known", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_delete_known(client, auth_headers):
    r = client.delete("/known/1", headers=auth_headers)
    assert r.status_code == 200
    assert "eliminato" in r.json()["message"]
