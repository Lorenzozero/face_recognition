"""
face_recognition-ng — OSINT Storage (SQLite)
Salva risultati OSINT strutturati (reverse image, social, Maigret)
per riuso, caching e reportistica.

Usage:
    db = OsintDatabase()
    run_id = db.save_run(image_hash, target_name, run_type, raw_json)
    db.save_evidence_batch(run_id, evidence_list)
    db.get_aggregate_stats()
    db.get_graph(run_id)  # export nodi/archi per Neo4j / Maltego
"""

import sqlite3
import os
import json
from typing import List, Dict, Optional
from datetime import datetime, timedelta

OSINT_DB_PATH = os.environ.get("FR_OSINT_DB_PATH", "osint_results.db")
OSINT_CACHE_TTL_HOURS = int(os.environ.get("OSINT_CACHE_TTL_HOURS", "24"))


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
            # ── Indici per performance ────────────────────────────────────
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_image_hash ON osint_runs(image_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_run_type ON osint_runs(run_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_created_at ON osint_runs(created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_risk_score ON osint_runs(risk_score DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_run_id ON osint_evidence(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_source ON osint_evidence(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_kind ON osint_evidence(kind)")
            conn.commit()

    # ── Cache TTL ────────────────────────────────────────────────────────────

    def _is_fresh(self, created_at: str) -> bool:
        try:
            ts = datetime.fromisoformat(created_at.replace(" ", "T"))
            return datetime.utcnow() - ts < timedelta(hours=OSINT_CACHE_TTL_HOURS)
        except Exception:
            return False

    # ── Salvataggio ─────────────────────────────────────────────────────────

    def save_run(self, image_hash: str, target_name: str, run_type: str, raw_json: Dict, risk_score: float = 0.0) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO osint_runs (image_hash, target_name, run_type, risk_score, raw_json) VALUES (?, ?, ?, ?, ?)",
                (image_hash, target_name, run_type, float(risk_score), json.dumps(raw_json)),
            )
            conn.commit()
            return cur.lastrowid

    def save_evidence_batch(self, run_id: int, evidence: List[Dict]) -> None:
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

    # ── Lettura / cache ──────────────────────────────────────────────────────

    def get_runs_by_image_hash(self, image_hash: str, run_type: Optional[str] = None) -> List[Dict]:
        query = "SELECT id, target_name, run_type, risk_score, created_at FROM osint_runs WHERE image_hash = ?"
        params = [image_hash]
        if run_type:
            query += " AND run_type = ?"
            params.append(run_type)
        query += " ORDER BY created_at DESC"
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {"id": r[0], "target_name": r[1], "run_type": r[2], "risk_score": r[3], "created_at": r[4]}
            for r in rows
        ]

    def get_fresh_run(self, image_hash: str, run_type: str) -> Optional[Dict]:
        runs = self.get_runs_by_image_hash(image_hash, run_type=run_type)
        for r in runs:
            if self._is_fresh(r["created_at"]):
                return self.load_raw_run(r["id"])
        return None

    def load_raw_run(self, run_id: int) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT raw_json FROM osint_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def get_evidence_for_run(self, run_id: int) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT source, url, kind, confidence, meta_json FROM osint_evidence WHERE run_id = ? ORDER BY confidence DESC",
                (run_id,),
            ).fetchall()
        return [
            {"source": r[0], "url": r[1], "kind": r[2], "confidence": r[3], "meta": json.loads(r[4] or "{}")}
            for r in rows
        ]

    def get_recent_runs(self, limit: int = 20) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, image_hash, target_name, run_type, risk_score, created_at FROM osint_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"id": r[0], "image_hash": r[1], "target_name": r[2], "run_type": r[3], "risk_score": r[4], "created_at": r[5]}
            for r in rows
        ]

    # ── Grafo nodi/archi (export per Neo4j / Maltego / vis.js) ──────────────

    def get_graph(self, run_id: int) -> Dict:
        """
        Restituisce nodi e archi per una run OSINT.
        Struttura:
          nodes: [{id, label, type, ...}]
          edges: [{source, target, label}]
        Tipi nodi: person, account, site, evidence
        """
        with sqlite3.connect(self.db_path) as conn:
            run = conn.execute(
                "SELECT id, target_name, run_type, risk_score, created_at FROM osint_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if not run:
                return {"nodes": [], "edges": []}

            evidence_rows = conn.execute(
                "SELECT id, source, url, kind, confidence, meta_json FROM osint_evidence WHERE run_id = ?",
                (run_id,),
            ).fetchall()

        person_node = {
            "id": f"person:{run[1]}",
            "label": run[1] or f"Target #{run[0]}",
            "type": "person",
            "risk_score": run[3],
        }
        nodes = [person_node]
        edges = []
        seen_sites = set()
        seen_accounts = set()

        for ev in evidence_rows:
            ev_id, source, url, kind, confidence, meta_raw = ev
            meta = json.loads(meta_raw or "{}")

            # Nodo sito/fonte
            site_id = f"site:{source}"
            if site_id not in seen_sites:
                nodes.append({"id": site_id, "label": source, "type": "site"})
                seen_sites.add(site_id)
            edges.append({"source": person_node["id"], "target": site_id, "label": kind or "found_on"})

            # Nodo account (per social e maigret)
            if kind in ("social_profile", "maigret_profile") and url:
                acc_id = f"account:{url}"
                if acc_id not in seen_accounts:
                    label = meta.get("username") or url
                    nodes.append({"id": acc_id, "label": label, "type": "account",
                                  "url": url, "platform": meta.get("platform") or meta.get("site"),
                                  "confidence": confidence})
                    seen_accounts.add(acc_id)
                edges.append({"source": site_id, "target": acc_id, "label": "profile"})

            # Nodo evidenza raw (reverse image)
            elif kind == "reverse_image" and url:
                ev_node_id = f"evidence:{ev_id}"
                nodes.append({"id": ev_node_id, "label": meta.get("title") or url[:60],
                               "type": "evidence", "url": url, "confidence": confidence})
                edges.append({"source": site_id, "target": ev_node_id, "label": "image_result"})

        return {
            "run_id": run_id,
            "target_name": run[1],
            "risk_score": run[3],
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    # ── Statistiche aggregate ────────────────────────────────────────────────

    def get_aggregate_stats(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM osint_runs").fetchone()[0]
            avg_risk = conn.execute("SELECT AVG(risk_score) FROM osint_runs").fetchone()[0] or 0.0
            max_risk = conn.execute("SELECT MAX(risk_score) FROM osint_runs").fetchone()[0] or 0.0

            by_type = conn.execute(
                "SELECT run_type, COUNT(*) as cnt FROM osint_runs GROUP BY run_type ORDER BY cnt DESC"
            ).fetchall()

            by_source = conn.execute(
                "SELECT source, COUNT(*) as cnt FROM osint_evidence GROUP BY source ORDER BY cnt DESC"
            ).fetchall()

            by_kind = conn.execute(
                "SELECT kind, COUNT(*) as cnt FROM osint_evidence GROUP BY kind ORDER BY cnt DESC"
            ).fetchall()

            top_risk = conn.execute(
                """SELECT target_name, risk_score, created_at FROM osint_runs
                   WHERE risk_score > 0 ORDER BY risk_score DESC LIMIT 5"""
            ).fetchall()

        return {
            "total_runs": total,
            "avg_risk_score": round(avg_risk, 3),
            "max_risk_score": round(max_risk, 3),
            "runs_by_type": [{"type": r[0], "count": r[1]} for r in by_type],
            "evidence_by_source": [{"source": r[0], "count": r[1]} for r in by_source],
            "evidence_by_kind": [{"kind": r[0], "count": r[1]} for r in by_kind],
            "top_risk_targets": [
                {"target_name": r[0], "risk_score": r[1], "created_at": r[2]}
                for r in top_risk
            ],
        }
