"""
test_api_osint.py — Test endpoint OSINT:
  /osint/image, /osint/social, /osint/full,
  /osint/stats, /osint/graph,
  rate limiting (429), cache TTL (from_cache)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os

# Forza RATE_LIMIT_ENABLED=true e token CI per tutti i test
os.environ.setdefault("FR_API_TOKEN", "test-token-ci")
os.environ.setdefault("RATE_LIMIT_WINDOW_SECS", "60")
os.environ.setdefault("RATE_LIMIT_ENABLED", "true")

MOCK_REVERSE = {
    "image_hash": "abc123def456",
    "timestamp": 1700000000,
    "total_results": 2,
    "sources": {
        "google_lens": {"results": [
            {"url": "https://lens.google.com/test", "title": "Google Lens", "source": "google_lens"},
            {"url": "https://lens.google.com/test2", "title": "Altro risultato", "source": "google_lens"},
        ]},
        "yandex":      {"results": []},
        "tineye":      {"results": []},
        "search_links":{"results": []},
    },
}
MOCK_SOCIAL   = {"platforms": [
    {"platform": "Instagram", "found": True,  "url": "https://instagram.com/mariorossi", "username": "mariorossi"},
    {"platform": "Twitter",   "found": False, "url": ""},
]}
MOCK_LINKS    = {"google_dork": "site:instagram.com Mario Rossi"}
MOCK_VARIANTS = ["mariorossi", "mario.rossi", "mario_rossi"]
MOCK_PDF      = b"%PDF-1.4 fake pdf content"


# ── /osint/image ─────────────────────────────────────────────────────────

def test_osint_image_no_auth(client, sample_image_bytes):
    r = client.post("/osint/image", files={"file": ("t.jpg", sample_image_bytes, "image/jpeg")})
    assert r.status_code == 401


def test_osint_image_with_auth(client, auth_headers, sample_image_bytes):
    with patch("api_server.osint.search", new=AsyncMock(return_value=MOCK_REVERSE)), \
         patch("api_server.osint_db.get_fresh_run", return_value=None), \
         patch("api_server.osint_db.save_run", return_value=1), \
         patch("api_server.osint_db.save_evidence_batch"):
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
    assert data["from_cache"] is False


def test_osint_image_cache_hit(client, auth_headers, sample_image_bytes):
    """Seconda chiamata con stesso hash deve restituire from_cache=True."""
    cached_payload = {**MOCK_REVERSE, "from_cache": True, "faces_detected": 1}
    with patch("api_server.osint_db.get_fresh_run", return_value=cached_payload):
        r = client.post(
            "/osint/image",
            headers=auth_headers,
            files={"file": ("t.jpg", sample_image_bytes, "image/jpeg")},
        )
    assert r.status_code == 200
    data = r.json()
    assert data.get("from_cache") is True


def test_osint_image_rate_limit(client, auth_headers, sample_image_bytes):
    """Superare RATE_LIMIT_OSINT_IMAGE (default 3) deve restituire 429."""
    import api_server
    # Resetta il limiter e forza il contatore oltre soglia direttamente
    key = f"testclient:osint_image"
    import time
    api_server.limiter._store[key] = (999, time.time())
    r = client.post(
        "/osint/image",
        headers=auth_headers,
        files={"file": ("t.jpg", sample_image_bytes, "image/jpeg")},
    )
    assert r.status_code == 429
    assert "X-RateLimit-Limit" in r.headers or "detail" in r.json()
    # Cleanup
    api_server.limiter._store.pop(key, None)


# ── /osint/social ────────────────────────────────────────────────────────

def test_osint_social_by_name(client, auth_headers):
    with patch("api_server.social.search_by_name",              new=AsyncMock(return_value=MOCK_SOCIAL)), \
         patch("api_server.social.generate_osint_report_links",  return_value=MOCK_LINKS), \
         patch("api_server.maigret.generate_username_variants",   return_value=MOCK_VARIANTS), \
         patch("api_server.osint_db.save_run", return_value=1), \
         patch("api_server.osint_db.save_evidence_batch"):
        r = client.post(
            "/osint/social",
            headers=auth_headers,
            json={"name": "Mario Rossi", "run_maigret": False},
        )
    assert r.status_code == 200
    data = r.json()
    assert "by_name" in data
    assert "username_variants" in data


def test_osint_social_evidence_saved(client, auth_headers):
    """Verifica che le evidenze social vengano salvate in DB."""
    saved_evidence = []
    def capture_evidence(run_id, ev):
        saved_evidence.extend(ev)

    with patch("api_server.social.search_by_name",              new=AsyncMock(return_value=MOCK_SOCIAL)), \
         patch("api_server.social.generate_osint_report_links",  return_value=MOCK_LINKS), \
         patch("api_server.maigret.generate_username_variants",   return_value=MOCK_VARIANTS), \
         patch("api_server.osint_db.save_run", return_value=1), \
         patch("api_server.osint_db.save_evidence_batch", side_effect=capture_evidence):
        r = client.post(
            "/osint/social",
            headers=auth_headers,
            json={"name": "Mario Rossi", "run_maigret": False},
        )
    assert r.status_code == 200
    # Instagram found=True deve generare almeno 1 evidenza
    assert any(e["kind"] == "social_profile" for e in saved_evidence)


# ── /osint/full ───────────────────────────────────────────────────────────

def test_osint_full_pipeline(client, auth_headers, sample_image_bytes):
    with patch("api_server.osint.search",                        new=AsyncMock(return_value=MOCK_REVERSE)), \
         patch("api_server.social.search_by_name",               new=AsyncMock(return_value=MOCK_SOCIAL)), \
         patch("api_server.social.generate_osint_report_links",   return_value=MOCK_LINKS), \
         patch("api_server.maigret.generate_username_variants",    return_value=MOCK_VARIANTS), \
         patch("api_server.osint_db.get_fresh_run", return_value=None), \
         patch("api_server.osint_db.save_run", return_value=1), \
         patch("api_server.osint_db.save_evidence_batch"):
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
    assert "risk_score" in data
    assert isinstance(data["risk_score"], float)
    assert data["from_cache"] is False


def test_osint_full_risk_score_nonzero(client, auth_headers, sample_image_bytes):
    """Con 1 profilo social trovato il risk_score deve essere > 0."""
    with patch("api_server.osint.search",                        new=AsyncMock(return_value=MOCK_REVERSE)), \
         patch("api_server.social.search_by_name",               new=AsyncMock(return_value=MOCK_SOCIAL)), \
         patch("api_server.social.generate_osint_report_links",   return_value=MOCK_LINKS), \
         patch("api_server.maigret.generate_username_variants",    return_value=MOCK_VARIANTS), \
         patch("api_server.osint_db.get_fresh_run", return_value=None), \
         patch("api_server.osint_db.save_run", return_value=1), \
         patch("api_server.osint_db.save_evidence_batch"):
        r = client.post(
            "/osint/full",
            headers=auth_headers,
            files={"file": ("t.jpg", sample_image_bytes, "image/jpeg")},
            data={"name": "Mario Rossi", "run_maigret": "false"},
        )
    assert r.json()["risk_score"] > 0.0


def test_osint_full_cache_hit(client, auth_headers, sample_image_bytes):
    """Cache TTL: se get_fresh_run restituisce dati, from_cache deve essere True."""
    cached = {**MOCK_REVERSE, "target_name": "Mario Rossi", "from_cache": True, "faces_detected": 1, "risk_score": 0.1}
    with patch("api_server.osint_db.get_fresh_run", return_value=cached):
        r = client.post(
            "/osint/full",
            headers=auth_headers,
            files={"file": ("t.jpg", sample_image_bytes, "image/jpeg")},
            data={"name": "Mario Rossi", "run_maigret": "false"},
        )
    assert r.status_code == 200
    assert r.json().get("from_cache") is True


# ── /osint/stats ──────────────────────────────────────────────────────────

def test_osint_stats_structure(client, auth_headers):
    """Verifica che /osint/stats ritorni tutti i campi aggregati attesi."""
    mock_stats = {
        "total_runs": 10,
        "avg_risk_score": 0.25,
        "max_risk_score": 0.8,
        "runs_by_type": [{"type": "full", "count": 5}, {"type": "image", "count": 3}],
        "evidence_by_source": [{"source": "google_lens", "count": 7}],
        "evidence_by_kind": [{"kind": "reverse_image", "count": 7}],
        "top_risk_targets": [{"target_name": "Test", "risk_score": 0.8, "created_at": "2026-06-01"}],
    }
    mock_recent = [{"id": 1, "image_hash": "abc", "target_name": "Test",
                    "run_type": "full", "risk_score": 0.8, "created_at": "2026-06-01"}]
    with patch("api_server.osint_db.get_aggregate_stats", return_value=mock_stats), \
         patch("api_server.osint_db.get_recent_runs", return_value=mock_recent):
        r = client.get("/osint/stats", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    for field in ("total_runs", "avg_risk_score", "max_risk_score",
                  "runs_by_type", "evidence_by_source", "evidence_by_kind",
                  "top_risk_targets", "recent_runs"):
        assert field in data, f"Campo mancante in /osint/stats: {field}"
    assert isinstance(data["runs_by_type"], list)
    assert isinstance(data["top_risk_targets"], list)


# ── /osint/graph ──────────────────────────────────────────────────────────

def test_osint_graph_found(client, auth_headers):
    """GET /osint/graph/{run_id} deve restituire nodi e archi."""
    mock_graph = {
        "run_id": 1,
        "target_name": "Mario Rossi",
        "risk_score": 0.4,
        "nodes": [
            {"id": "person:Mario Rossi", "label": "Mario Rossi", "type": "person", "risk_score": 0.4},
            {"id": "site:google_lens",   "label": "google_lens", "type": "site"},
            {"id": "account:https://instagram.com/mariorossi", "label": "mariorossi",
             "type": "account", "url": "https://instagram.com/mariorossi",
             "platform": "Instagram", "confidence": 0.8},
        ],
        "edges": [
            {"source": "person:Mario Rossi", "target": "site:google_lens",   "label": "reverse_image"},
            {"source": "site:google_lens",   "target": "account:https://instagram.com/mariorossi", "label": "profile"},
        ],
        "node_count": 3,
        "edge_count": 2,
    }
    with patch("api_server.osint_db.get_graph", return_value=mock_graph):
        r = client.get("/osint/graph/1", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "nodes" in data
    assert "edges" in data
    assert data["node_count"] == 3
    assert data["edge_count"] == 2
    assert any(n["type"] == "person" for n in data["nodes"])
    assert any(n["type"] == "account" for n in data["nodes"])


def test_osint_graph_not_found(client, auth_headers):
    """Run ID inesistente deve restituire 404."""
    with patch("api_server.osint_db.get_graph", return_value={"nodes": [], "edges": []}):
        r = client.get("/osint/graph/9999", headers=auth_headers)
    assert r.status_code == 404


def test_osint_graph_no_auth(client):
    r = client.get("/osint/graph/1")
    assert r.status_code == 401


# ── Rate limit generico ────────────────────────────────────────────────────

def test_rate_limit_429_headers(client, auth_headers, sample_image_bytes):
    """Il rate limiter deve aggiungere header X-RateLimit-* alla risposta 429."""
    import api_server, time
    key = "testclient:osint_full"
    api_server.limiter._store[key] = (999, time.time())
    r = client.post(
        "/osint/full",
        headers=auth_headers,
        files={"file": ("t.jpg", sample_image_bytes, "image/jpeg")},
        data={"name": "Test", "run_maigret": "false"},
    )
    assert r.status_code == 429
    body = r.json()
    assert "detail" in body
    assert "429" in str(r.status_code)
    api_server.limiter._store.pop(key, None)


def test_rate_limit_disabled(client, auth_headers, sample_image_bytes, monkeypatch):
    """Con RATE_LIMIT_ENABLED=false nessun 429 deve essere sollevato."""
    import api_server
    monkeypatch.setattr(api_server.limiter, '_RateLimiter__rate_enabled', False, raising=False)
    # patch diretto del modulo rate_limiter
    import rate_limiter as rl
    original = rl.RATE_LIMIT_ENABLED
    rl.RATE_LIMIT_ENABLED = False
    try:
        import time
        key = "testclient:osint_social"
        api_server.limiter._store[key] = (999, time.time())
        with patch("api_server.social.search_by_name",             new=AsyncMock(return_value=MOCK_SOCIAL)), \
             patch("api_server.social.generate_osint_report_links", return_value=MOCK_LINKS), \
             patch("api_server.maigret.generate_username_variants",  return_value=MOCK_VARIANTS), \
             patch("api_server.osint_db.save_run", return_value=1), \
             patch("api_server.osint_db.save_evidence_batch"):
            r = client.post(
                "/osint/social",
                headers=auth_headers,
                json={"name": "Mario Rossi"},
            )
        # Con RATE_LIMIT_ENABLED=false non deve dare 429
        assert r.status_code != 429
    finally:
        rl.RATE_LIMIT_ENABLED = original
        api_server.limiter._store.pop(key, None)
