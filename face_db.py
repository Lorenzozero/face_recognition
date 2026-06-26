"""
face_recognition-ng — Database Volti Noti (SQLite)
Salva encoding facciali con nome associato.
Usato per il riconoscimento in tempo reale durante lo streaming.

Usage:
    db = FaceDatabase()
    db.register("Mario Rossi", encoding_array)
    match = db.find_match(encoding_array)  # -> {"name": ..., "distance": ...} oppure None
"""

import sqlite3
import numpy as np
import json
import os
from typing import Optional, List, Dict

DB_PATH = os.environ.get("FR_DB_PATH", "known_faces.db")
DEFAULT_TOLERANCE = float(os.environ.get("FR_TOLERANCE", "0.5"))


class FaceDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS known_faces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    encoding TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def register(self, name: str, encoding: np.ndarray) -> int:
        """Registra un nuovo volto noto nel database."""
        encoding_json = json.dumps(encoding.tolist())
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO known_faces (name, encoding) VALUES (?, ?)",
                (name, encoding_json)
            )
            conn.commit()
            return cursor.lastrowid

    def list_known(self) -> List[Dict]:
        """Restituisce tutti i volti noti registrati."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, name, created_at FROM known_faces ORDER BY created_at DESC"
            ).fetchall()
        return [{"id": r[0], "name": r[1], "created_at": r[2]} for r in rows]

    def delete(self, face_id: int) -> bool:
        """Elimina un volto dal database per ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM known_faces WHERE id = ?", (face_id,))
            conn.commit()
        return True

    def find_match(self, encoding: np.ndarray, tolerance: float = DEFAULT_TOLERANCE) -> Optional[Dict]:
        """Cerca il volto più simile nel database. Restituisce None se nessuna corrispondenza."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT id, name, encoding FROM known_faces").fetchall()

        if not rows:
            return None

        known_encodings = [np.array(json.loads(r[2])) for r in rows]
        distances = np.array([
            float(face_recognition.face_distance([k], encoding)[0])
            for k in known_encodings
        ])

        best_idx = int(np.argmin(distances))
        best_distance = distances[best_idx]

        if best_distance <= tolerance:
            return {
                "id": rows[best_idx][0],
                "name": rows[best_idx][1],
                "distance": round(float(best_distance), 4),
            }
        return None


# Importa face_recognition solo quando necessario (evita import circolare)
import face_recognition
