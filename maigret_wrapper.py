"""
face_recognition-ng — Maigret Wrapper (Fase 3)
Wrapper async per Maigret: dato uno o più username,
cerca la presenza su 3000+ siti e social network.

Installazione Maigret:
    pip install maigret

Usage:
    wrapper = MaigretWrapper()
    results = await wrapper.search("mario_rossi")
    results = await wrapper.search_multiple(["mario_rossi", "mariorossi", "m.rossi"])
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from typing import List, Dict, Optional


class MaigretWrapper:
    """
    Wrapper per Maigret (https://github.com/soxoj/maigret).
    Esegue la ricerca in un subprocess per non bloccare FastAPI.
    """

    def __init__(self, timeout: int = 60, top_sites: int = 500):
        self.timeout = timeout
        self.top_sites = top_sites  # Limita ai top N siti per velocità
        self._maigret_available = self._check_maigret()

    def _check_maigret(self) -> bool:
        """Verifica se Maigret è installato."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "maigret", "--version"],
                capture_output=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    async def search(self, username: str) -> Dict:
        """
        Cerca un username su tutti i siti supportati da Maigret.
        Restituisce i profili trovati con URL.
        """
        if not self._maigret_available:
            return {
                "username": username,
                "available": False,
                "message": "Maigret non installato. Esegui: pip install maigret",
                "install_url": "https://github.com/soxoj/maigret",
                "results": [],
            }

        return await asyncio.get_event_loop().run_in_executor(
            None, self._run_maigret_sync, username
        )

    async def search_multiple(self, usernames: List[str]) -> Dict:
        """Cerca più username in parallelo."""
        tasks = [self.search(u) for u in usernames]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            "usernames": usernames,
            "results": {
                u: r if not isinstance(r, Exception) else {"error": str(r)}
                for u, r in zip(usernames, results)
            }
        }

    def _run_maigret_sync(self, username: str) -> Dict:
        """Esegue Maigret in modo sincrono (chiamato in un thread executor)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, f"{username}.json")
            cmd = [
                sys.executable, "-m", "maigret",
                username,
                "--json", output_file,
                "--top-sites", str(self.top_sites),
                "--no-progressbar",
                "--timeout", "10",
            ]
            try:
                subprocess.run(cmd, capture_output=True, timeout=self.timeout, cwd=tmpdir)
            except subprocess.TimeoutExpired:
                pass  # Usa i risultati parziali

            # Leggi risultati JSON
            if os.path.exists(output_file):
                with open(output_file) as f:
                    raw = json.load(f)
                return self._parse_maigret_output(username, raw)
            else:
                return {"username": username, "results": [], "error": "Nessun output da Maigret"}

    def _parse_maigret_output(self, username: str, raw: Dict) -> Dict:
        """Parsa l'output JSON di Maigret in formato strutturato."""
        found = []
        for site_name, site_data in raw.items():
            if isinstance(site_data, dict) and site_data.get("status") == "Claimed":
                found.append({
                    "site": site_name,
                    "url": site_data.get("url_user", ""),
                    "category": site_data.get("category", ""),
                    "country": site_data.get("country", ""),
                })

        # Raggruppa per categoria
        by_category = {}
        for r in found:
            cat = r.get("category", "Other") or "Other"
            by_category.setdefault(cat, []).append(r)

        return {
            "username": username,
            "available": True,
            "total_found": len(found),
            "results": found,
            "by_category": by_category,
            "top_social": [
                r for r in found
                if r.get("category") in ("social", "Social Networks", "Dating")
            ][:10],
        }

    def generate_username_variants(self, full_name: str) -> List[str]:
        """
        Dato un nome completo, genera varianti di username comuni.
        Es: 'Mario Rossi' -> ['mariorossi', 'mario.rossi', 'mario_rossi', 'mrossi', ...]
        """
        parts = full_name.lower().split()
        if len(parts) < 2:
            return [parts[0]] if parts else []

        first, last = parts[0], parts[-1]
        variants = [
            f"{first}{last}",
            f"{first}.{last}",
            f"{first}_{last}",
            f"{first[0]}{last}",
            f"{first}{last[0]}",
            f"{last}{first}",
            f"{last}.{first}",
            f"{last}_{first}",
            first,
            last,
        ]
        return list(dict.fromkeys(variants))  # rimuove duplicati
