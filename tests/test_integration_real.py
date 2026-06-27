"""
test_integration_real.py — Test di integrazione con InsightFace REALE.

Questi test usano le immagini in tests/test_images/ e InsightFace vero.
Girano nel job 'integration' della CI (Python 3.11, con cache modelli)
e in locale dopo: pip install -r requirements_ng.txt

Skippati automaticamente se InsightFace non e' installato.
"""
import io
import os
import pytest
import numpy as np
from pathlib import Path

# Skip tutto il file se insightface non e' installato
pytest.importorskip("insightface", reason="insightface non installato — esegui: pip install insightface onnxruntime")

TEST_IMAGES = Path(__file__).parent / "test_images"


@pytest.fixture(scope="module")
def fr():
    """Importa il backend InsightFace reale (lazy-load modello)."""
    import face_recognition
    return face_recognition


# ── face_locations ────────────────────────────────────────────────────────────

def test_detect_face_obama(fr):
    """InsightFace deve trovare esattamente 1 volto in obama.jpg."""
    img = fr.load_image_file(TEST_IMAGES / "obama.jpg")
    locations = fr.face_locations(img)
    assert len(locations) == 1, f"Atteso 1 volto, trovati {len(locations)}"
    top, right, bottom, left = locations[0]
    assert top >= 0 and left >= 0
    assert bottom > top and right > left


def test_detect_face_biden(fr):
    """InsightFace deve trovare almeno 1 volto in biden.jpg."""
    img = fr.load_image_file(TEST_IMAGES / "biden.jpg")
    locations = fr.face_locations(img)
    assert len(locations) >= 1, f"Nessun volto trovato in biden.jpg"


def test_detect_no_face_on_blank():
    """Su un'immagine bianca non devono essere trovati volti."""
    import face_recognition
    blank = np.ones((200, 200, 3), dtype=np.uint8) * 255
    locations = face_recognition.face_locations(blank)
    assert len(locations) == 0


# ── face_encodings ───────────────────────────────────────────────────────────

def test_encoding_shape(fr):
    """Gli encoding InsightFace devono essere vettori 512D normalizzati."""
    img = fr.load_image_file(TEST_IMAGES / "obama.jpg")
    encodings = fr.face_encodings(img)
    assert len(encodings) == 1
    enc = encodings[0]
    assert enc.shape == (512,)
    # Embedding normalizzato: norma ~= 1.0
    norm = float(np.linalg.norm(enc))
    assert 0.99 < norm < 1.01, f"Embedding non normalizzato: norma={norm}"


# ── compare_faces (stesso soggetto) ───────────────────────────────────────────

def test_same_person_matches(fr):
    """obama.jpg e obama2.jpg sono la stessa persona: compare_faces deve dare True."""
    img1 = fr.load_image_file(TEST_IMAGES / "obama.jpg")
    img2 = fr.load_image_file(TEST_IMAGES / "obama2.jpg")
    enc1 = fr.face_encodings(img1)
    enc2 = fr.face_encodings(img2)
    assert enc1 and enc2, "Nessun encoding trovato"
    results = fr.compare_faces(enc1, enc2[0], tolerance=0.6)
    assert results[0] is True, "Obama non riconosciuto come se stesso"


def test_different_persons_no_match(fr):
    """obama.jpg e biden.jpg sono persone diverse: compare_faces deve dare False."""
    img_obama = fr.load_image_file(TEST_IMAGES / "obama.jpg")
    img_biden = fr.load_image_file(TEST_IMAGES / "biden.jpg")
    enc_obama = fr.face_encodings(img_obama)
    enc_biden = fr.face_encodings(img_biden)
    assert enc_obama and enc_biden
    results = fr.compare_faces(enc_obama, enc_biden[0], tolerance=0.6)
    assert results[0] is False, "Obama e Biden non dovrebbero corrispondere"


# ── face_distance ─────────────────────────────────────────────────────────────────

def test_distance_same_person_low(fr):
    """Distanza obama vs obama2 deve essere < 0.4 (stessa persona)."""
    img1 = fr.load_image_file(TEST_IMAGES / "obama.jpg")
    img2 = fr.load_image_file(TEST_IMAGES / "obama2.jpg")
    enc1 = fr.face_encodings(img1)[0]
    enc2 = fr.face_encodings(img2)[0]
    dist = fr.face_distance([enc1], enc2)[0]
    assert dist < 0.4, f"Distanza troppo alta per la stessa persona: {dist:.4f}"


def test_distance_different_persons_high(fr):
    """Distanza obama vs biden deve essere > 0.4 (persone diverse)."""
    img_obama = fr.load_image_file(TEST_IMAGES / "obama.jpg")
    img_biden = fr.load_image_file(TEST_IMAGES / "biden.jpg")
    enc_obama = fr.face_encodings(img_obama)[0]
    enc_biden = fr.face_encodings(img_biden)[0]
    dist = fr.face_distance([enc_obama], enc_biden)[0]
    assert dist > 0.4, f"Distanza troppo bassa per persone diverse: {dist:.4f}"


# ── report PDF con dati reali ─────────────────────────────────────────────────────

def test_build_pdf_with_real_face(fr):
    """build_pdf con encoding reale di Obama deve produrre un PDF valido."""
    from report_generator import build_pdf
    img = fr.load_image_file(TEST_IMAGES / "obama.jpg")
    img_bytes = open(TEST_IMAGES / "obama.jpg", "rb").read()

    osint_data = {
        "target_name": "Barack Obama",
        "faces_detected": 1,
        "reverse_image": {
            "image_hash": "abc123",
            "timestamp": 1700000000,
            "total_results": 1,
            "sources": {
                "google_lens": {"results": [{"url": "https://lens.google.com/test", "title": "Google Lens", "source": "google_lens"}]},
                "yandex": {"results": []},
                "tineye": {"results": []},
                "search_links": {"results": []},
            },
        },
        "social": {"platforms": [
            {"platform": "Twitter",  "found": True,  "url": "https://twitter.com/BarackObama"},
            {"platform": "Facebook", "found": True,  "url": "https://facebook.com/barackobama"},
            {"platform": "Instagram","found": False, "url": ""},
        ]},
        "osint_links": {"google_dork": "site:twitter.com Barack Obama"},
        "username_variants": ["barackobama", "barack.obama", "b.obama"],
        "maigret": None,
    }

    pdf_bytes = build_pdf(osint_data, target_image_bytes=img_bytes)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 10_000  # PDF reale con grafico > 10KB
