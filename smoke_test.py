"""
smoke_test.py — Verifica end-to-end del server face_recognition-ng v4.5

Usage:
  1. Avvia il server:
       FR_API_TOKEN=changeme python api_server.py
  2. In un altro terminale:
       python smoke_test.py

Controlla:
  /health, /encode, /detect, /compare, /register, /known,
  /osint/image (cache miss + cache hit), /osint/social,
  /osint/full (risk_score), /osint/stats (campi aggregati),
  /osint/graph (nodi/archi), /report/pdf,
  rate limit 429 (RATE_LIMIT_ENABLED=true)
"""

import sys
import io
import httpx
from pathlib import Path

BASE_URL = "http://localhost:8000"
TOKEN    = "changeme"
HEADERS  = {"Authorization": f"Bearer {TOKEN}"}
IMG_PATH = Path("tests/test_images/obama.jpg")

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  \u2705  {name}")
        passed += 1
    else:
        print(f"  \u274c  {name}" + (f" \u2014 {detail}" if detail else ""))
        failed += 1


def section(title):
    print(f"\n{'='*55}\n  {title}\n{'='*55}")


with httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=60) as c:

    # ------------------------------------------------------------------ #
    section("/health")
    try:
        r = c.get("/health")
        check("status 200", r.status_code == 200)
        check("status=ok", r.json().get("status") == "ok")
        check("version presente", "version" in r.json())
    except Exception as e:
        check("connessione al server", False, str(e))
        print("\nERRORE: server non raggiungibile. Avvialo con: python api_server.py")
        sys.exit(1)

    # ------------------------------------------------------------------ #
    with open(IMG_PATH, "rb") as f:
        img_bytes = f.read()

    section("/encode")
    r = c.post("/encode", files={"file": ("obama.jpg", img_bytes, "image/jpeg")})
    check("status 200", r.status_code == 200)
    enc_data = r.json()
    check("faces_found >= 1", enc_data.get("faces_found", 0) >= 1, f"trovati: {enc_data.get('faces_found')}")
    check("encoding 512D", len(enc_data.get("encodings", [[]])[0]) == 512)
    encoding_a = enc_data["encodings"][0]

    section("/detect")
    r = c.post("/detect", files={"file": ("obama.jpg", img_bytes, "image/jpeg")})
    check("status 200", r.status_code == 200)
    check("faces_found >= 1", r.json().get("faces_found", 0) >= 1)

    section("/compare")
    r = c.post("/compare", json={"encoding_a": encoding_a, "encoding_b": encoding_a, "tolerance": 0.6})
    check("status 200", r.status_code == 200)
    cmp = r.json()
    check("match=True (stesso encoding)", cmp.get("match") is True)
    check("distance~0.0", cmp.get("distance", 1.0) < 0.01, f"distance={cmp.get('distance')}")

    section("/register + /known")
    r = c.post("/register?name=Obama+Test", files={"file": ("obama.jpg", img_bytes, "image/jpeg")})
    check("register status 200", r.status_code == 200)
    face_id = r.json().get("id")
    check("id restituito", face_id is not None)
    r = c.get("/known")
    check("known status 200", r.status_code == 200)
    check("volto in lista", any(f["id"] == face_id for f in r.json()))

    # ------------------------------------------------------------------ #
    section("/osint/image — prima chiamata (cache miss)")
    r = c.post("/osint/image", files={"file": ("obama.jpg", img_bytes, "image/jpeg")})
    check("status 200", r.status_code == 200)
    osint = r.json()
    check("faces_detected >= 1", osint.get("faces_detected", 0) >= 1)
    check("sources presente", "sources" in osint)
    check("from_cache=False", osint.get("from_cache") is False, f"from_cache={osint.get('from_cache')}")
    first_run_cache = osint.get("from_cache")

    section("/osint/image — seconda chiamata (cache hit atteso)")
    r2 = c.post("/osint/image", files={"file": ("obama.jpg", img_bytes, "image/jpeg")})
    check("status 200", r2.status_code == 200)
    osint2 = r2.json()
    check("from_cache=True (TTL cache)", osint2.get("from_cache") is True,
          f"from_cache={osint2.get('from_cache')} (normale se TTL=0 o server riavviato)")

    section("/osint/social")
    r = c.post("/osint/social", json={"name": "Barack Obama", "run_maigret": False})
    check("status 200", r.status_code == 200)
    soc = r.json()
    check("by_name presente", "by_name" in soc)
    check("username_variants presente", "username_variants" in soc)

    section("/osint/full (pipeline + risk_score)")
    r = c.post(
        "/osint/full",
        files={"file": ("obama.jpg", img_bytes, "image/jpeg")},
        data={"name": "Barack Obama", "run_maigret": "false"},
    )
    check("status 200", r.status_code == 200)
    full = r.json()
    check("target_name corretto", full.get("target_name") == "Barack Obama")
    check("reverse_image presente", "reverse_image" in full)
    check("social presente", "social" in full)
    check("risk_score è float", isinstance(full.get("risk_score"), float))
    check("from_cache presente", "from_cache" in full)

    # Recupera il run_id per testare /osint/graph
    run_id = None

    section("/osint/stats (campi aggregati)")
    r = c.get("/osint/stats")
    check("status 200", r.status_code == 200)
    stats = r.json()
    for field in ("total_runs", "avg_risk_score", "max_risk_score",
                  "runs_by_type", "evidence_by_source", "evidence_by_kind",
                  "top_risk_targets", "recent_runs"):
        check(f"campo '{field}' presente", field in stats, f"mancante: {field}")
    check("total_runs >= 1", stats.get("total_runs", 0) >= 1)
    recent = stats.get("recent_runs", [])
    if recent:
        run_id = recent[0].get("id")
    check("recent_runs non vuota", len(recent) >= 1)

    section("/osint/graph/{run_id} (nodi e archi)")
    if run_id:
        r = c.get(f"/osint/graph/{run_id}")
        check("status 200", r.status_code == 200)
        graph = r.json()
        check("nodes presente", "nodes" in graph)
        check("edges presente", "edges" in graph)
        check("node_count >= 1", graph.get("node_count", 0) >= 1)
        check("nodo person presente", any(n.get("type") == "person" for n in graph.get("nodes", [])))
    else:
        check("graph test saltato (run_id non disponibile)", True, "nessuna run recente")

    section("/osint/graph/9999 — run inesistente (404)")
    r = c.get("/osint/graph/9999")
    check("status 404", r.status_code == 404)

    # ------------------------------------------------------------------ #
    section("/report/pdf (PDF reale generato)")
    r = c.post(
        "/report/pdf",
        files={"file": ("obama.jpg", img_bytes, "image/jpeg")},
        data={"name": "Barack Obama", "run_maigret": "false"},
    )
    check("status 200", r.status_code == 200)
    check("content-type=application/pdf", "application/pdf" in r.headers.get("content-type", ""))
    check("magic bytes %PDF", r.content[:4] == b"%PDF")
    check("dimensione > 10KB", len(r.content) > 10_000, f"{len(r.content)} bytes")
    out_path = Path("smoke_test_report.pdf")
    out_path.write_bytes(r.content)
    print(f"  INFO  PDF salvato in: {out_path.resolve()}")

    # ------------------------------------------------------------------ #
    section("Rate limit 429 (RATE_LIMIT_ENABLED=true)")
    rl_triggered = False
    for i in range(10):
        r = c.post("/osint/social", json={"name": "test"})
        if r.status_code == 429:
            rl_triggered = True
            retry_after = r.headers.get("Retry-After") or r.json().get("detail", "")
            break
    check("429 ricevuto dopo N richieste rapide", rl_triggered,
          "(normale se RATE_LIMIT_ENABLED=false o window scaduta)")
    if rl_triggered:
        check("detail presente nel body 429", "detail" in r.json())

    # ------------------------------------------------------------------ #
    section("/delete known")
    if face_id:
        r = c.delete(f"/known/{face_id}")
        check("delete status 200", r.status_code == 200)


print(f"\n{'='*55}")
print(f"  Risultato: {passed} \u2705 PASS  |  {failed} \u274c FAIL")
print(f"{'='*55}\n")
sys.exit(0 if failed == 0 else 1)
