"""
face_recognition-ng — OSINT Storage (SQLite)
Salva risultati OSINT strutturati (reverse image, social, Maigret)
per riuso, caching e reportistica.

Usage:
    db = OsintDatabase()
    run_id = db.save_image_osint(image_hash, osint_json)
    db.save_social_profiles(run_id, profiles)
    db.save_maigret_results(run_id, maigret_json)
"""

import sqlite3
import os
import json
from typing import List, Dict, Optional

OSINT_DB_PATH = os.environ.get("FR_OSINT_DB_PATH", "osint_results.db")


class OsintDatabase:
    def __init__(self, db_path: str = OSINT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS osint_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_hash TEXT,
                    target_name TEXT,
                    run_type TEXT,
                    risk_score REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    raw_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS osint_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    url TEXT NOT NULL,
                    kind TEXT,
                    confidence REAL,
                    meta_json TEXT,
                    FOREIGN KEY(run_id) REFERENCES osint_runs(id)
                )
                """
            )
            conn.commit()

    def save_run(self, image_hash: str, target_name: str, run_type: str, raw_json: Dict, risk_score: float = 0.0) -> int:
        """Salva una run OSINT generica (image/social/full) e restituisce l'ID."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO osint_runs (image_hash, target_name, run_type, risk_score, raw_json) VALUES (?, ?, ?, ?, ?)",
                (image_hash, target_name, run_type, float(risk_score), json.dumps(raw_json)),
            )
            conn.commit()
            return cur.lastrowid

    def save_evidence_batch(self, run_id: int, evidence: List[Dict]) -> None:
        """Salva una lista di evidenze (fonte, url, tipo, confidence, meta)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                "INSERT INTO osint_evidence (run_id, source, url, kind, confidence, meta_json) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id,
                        e.get("source", ""),
                        e.get("url", ""),
                        e.get("kind"),
                        float(e.get("confidence", 0.0) or 0.0),
                        json.dumps(e.get("meta", {})),
                    )
                    for e in evidence
                ],
            )
            conn.commit()

    def get_runs_by_image_hash(self, image_hash: str) -> List[Dict]:
        """Restituisce tutte le run OSINT associate a un certo image_hash (per caching)."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, target_name, run_type, risk_score, created_at FROM osint_runs WHERE image_hash = ? ORDER BY created_at DESC",
                (image_hash,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "target_name": r[1],
                "run_type": r[2],
                "risk_score": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]

    def get_evidence_for_run(self, run_id: int) -> List[Dict]:
        """Restituisce evidenze strutturate per una run."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT source, url, kind, confidence, meta_json FROM osint_evidence WHERE run_id = ? ORDER BY confidence DESC",
                (run_id,),
            ).fetchall()
        return [
            {
                "source": r[0],
                "url": r[1],
                "kind": r[2],
                "confidence": r[3],
                "meta": json.loads(r[4] or "{}"),
            }
            for r in rows
        ]

    def load_raw_run(self, run_id: int) -> Optional[Dict]:
        """Carica il raw_json di una run (per rigenerare report o rispondere a API)."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT raw_json FROM osint_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row[0])

    def get_recent_runs(self, limit: int = 20) -> List[Dict]:
        """Restituisce le run OSINT più recenti (per dashboard o endpoint /osint/stats)."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, image_hash, target_name, run_type, risk_score, created_at FROM osint_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "image_hash": r[1],
                "target_name": r[2],
                "run_type": r[3],
                "risk_score": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]
