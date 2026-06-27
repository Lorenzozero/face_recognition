"""
smoke_test.py — Verifica end-to-end del server face_recognition-ng.

Usage:
  1. Avvia il server in un terminale:
       FR_API_TOKEN=changeme python api_server.py

  2. In un altro terminale esegui:
       python smoke_test.py

Controlla: /health, /encode, /detect, /compare, /register, /known,
           /osint/image, /report/pdf
"""

import sys
import io
import json
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
        print(f"  PASS  {name}")
        passed += 1
    else:
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))
        failed += 1


def section(title):
    print(f"\n{'='*50}\n  {title}\n{'='*50}")


with httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=60) as c:

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

    section("/encode")
    with open(IMG_PATH, "rb") as f:
        img_bytes = f.read()
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
    known = r.json()
    check("volto in lista", any(f["id"] == face_id for f in known))

    section("/osint/image (links generati, no HTTP esterno)")
    r = c.post("/osint/image", files={"file": ("obama.jpg", img_bytes, "image/jpeg")})
    check("status 200", r.status_code == 200)
    osint = r.json()
    check("faces_detected >= 1", osint.get("faces_detected", 0) >= 1)
    check("sources presente", "sources" in osint)

    section("/report/pdf (PDF reale generato)")
    r = c.post(
        "/report/pdf",
        files={"file": ("obama.jpg", img_bytes, "image/jpeg")},
        data={"name": "Barack Obama", "run_maigret": "false"},
    )
    check("status 200", r.status_code == 200)
    check("content-type=application/pdf", r.headers.get("content-type") == "application/pdf")
    check("magic bytes %PDF", r.content[:4] == b"%PDF")
    check("dimensione > 10KB", len(r.content) > 10_000, f"{len(r.content)} bytes")

    # Salva il PDF per ispezione visiva
    out_path = Path("smoke_test_report.pdf")
    out_path.write_bytes(r.content)
    print(f"  INFO  PDF salvato in: {out_path.resolve()}")

    section("/delete known")
    if face_id:
        r = c.delete(f"/known/{face_id}")
        check("delete status 200", r.status_code == 200)


print(f"\n{'='*50}")
print(f"  Risultato: {passed} PASS, {failed} FAIL")
print(f"{'='*50}\n")
sys.exit(0 if failed == 0 else 1)
