"""
face_recognition-ng — OSINT Engine (Fase 3)
Ricerca reverse image su più fonti:
  - Google Lens (via scraping headers)
  - Yandex Images
  - TinEye
  - PimEyes (public results)

Usage:
    engine = OsintEngine()
    results = await engine.search(image_bytes)
"""

import asyncio
import base64
import io
import hashlib
import os
import time
from typing import List, Dict, Optional
from dataclasses import dataclass, field

import httpx
from PIL import Image


OSINT_ENABLE_EXTERNAL = os.getenv("OSINT_ENABLE_EXTERNAL", "true").lower() == "true"
OSINT_TIMEOUT = int(os.getenv("OSINT_TIMEOUT", "30"))


@dataclass
class OsintResult:
    source: str
    url: str
    title: str = ""
    thumbnail: str = ""
    confidence: float = 0.0
    extra: Dict = field(default_factory=dict)


class OsintEngine:
    """
    Motore OSINT per reverse image search su più fonti.
    Usa solo endpoint pubblici — nessuna API key richiesta per le funzioni base.

    Comportamento configurabile via ENV:
    - OSINT_ENABLE_EXTERNAL=false -> niente chiamate esterne, solo link generati
    - OSINT_TIMEOUT=30            -> timeout httpx per motori esterni
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8",
    }

    def __init__(self, timeout: Optional[int] = None):
        # Se non specificato, usa OSINT_TIMEOUT da ENV
        self.timeout = timeout if timeout is not None else OSINT_TIMEOUT

    async def search(self, image_bytes: bytes) -> Dict:
        """
        Esegue la ricerca su tutte le fonti in parallelo.
        Restituisce un dict con risultati aggregati per fonte.

        Se OSINT_ENABLE_EXTERNAL=false, salta Google Lens/Yandex/TinEye
        e ritorna solo i link generati (_build_search_links).
        """
        img_hash = hashlib.md5(image_bytes).hexdigest()[:8]

        if not OSINT_ENABLE_EXTERNAL:
            # Solo link di ricerca (PimEyes, Bing, Google Images)
            links = await self._build_search_links(image_bytes)
            return {
                "image_hash": img_hash,
                "timestamp": int(time.time()),
                "sources": {"search_links": links},
                "total_results": len(links.get("results", [])),
                "external_calls": False,
            }

        tasks = [
            self._search_google_lens(image_bytes),
            self._search_yandex(image_bytes),
            self._search_tineye(image_bytes),
            self._build_search_links(image_bytes),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {
            "image_hash": img_hash,
            "timestamp": int(time.time()),
            "sources": {},
            "total_results": 0,
            "external_calls": True,
        }

        source_names = ["google_lens", "yandex", "tineye", "search_links"]
        for name, result in zip(source_names, results):
            if isinstance(result, Exception):
                output["sources"][name] = {"error": str(result), "results": []}
            else:
                output["sources"][name] = result
                output["total_results"] += len(result.get("results", []))

        return output

    async def _search_google_lens(self, image_bytes: bytes) -> Dict:
        """
        Google Lens reverse image search.
        Carica l'immagine e ottieni l'URL di ricerca visiva.
        """
        try:
            async with httpx.AsyncClient(headers=self.HEADERS, timeout=self.timeout, follow_redirects=True) as client:
                files = {"encoded_image": ("face.jpg", image_bytes, "image/jpeg")}
                resp = await client.post(
                    "https://lens.google.com/upload",
                    files=files,
                    params={"ep": "ccm", "re": "df", "s": "4", "st": str(int(time.time() * 1000))},
                )
                lens_url = str(resp.url)
                return {
                    "results": [{"url": lens_url, "title": "Google Lens — apri per risultati visivi", "source": "google_lens"}],
                    "search_url": lens_url,
                    "note": "Apri search_url nel browser per vedere i risultati completi di Google Lens",
                }
        except Exception as e:
            return {"results": [], "error": str(e)}

    async def _search_yandex(self, image_bytes: bytes) -> Dict:
        """
        Yandex Images reverse search.
        Carica immagine e ottieni URL risultati.
        """
        try:
            async with httpx.AsyncClient(headers=self.HEADERS, timeout=self.timeout, follow_redirects=True) as client:
                files = {"upfile": ("face.jpg", image_bytes, "image/jpeg")}
                resp = await client.post(
                    "https://yandex.com/images/search",
                    files=files,
                    params={"rpt": "imageview", "format": "json"},
                )
                search_url = str(resp.url)
                return {
                    "results": [{"url": search_url, "title": "Yandex Images — apri per risultati", "source": "yandex"}],
                    "search_url": search_url,
                    "note": "Yandex ha ottimo riconoscimento facciale per profili russi/est-europei",
                }
        except Exception as e:
            return {"results": [], "error": str(e)}

    async def _search_tineye(self, image_bytes: bytes) -> Dict:
        """
        TinEye reverse image search.
        """
        try:
            async with httpx.AsyncClient(headers=self.HEADERS, timeout=self.timeout, follow_redirects=True) as client:
                files = {"image": ("face.jpg", image_bytes, "image/jpeg")}
                resp = await client.post(
                    "https://tineye.com/search",
                    files=files,
                )
                search_url = str(resp.url)
                count_text = ""
                try:
                    import re
                    match = re.search(r"(\d+)\s+result", resp.text)
                    if match:
                        count_text = f"{match.group(1)} risultati trovati"
                except Exception:
                    pass
                return {
                    "results": [{"url": search_url, "title": f"TinEye — {count_text or 'apri per risultati'}", "source": "tineye"}],
                    "search_url": search_url,
                }
        except Exception as e:
            return {"results": [], "error": str(e)}

    async def _build_search_links(self, image_bytes: bytes) -> Dict:
        """
        Genera link diretti per apertura manuale su varie piattaforme.
        Usa data URL base64 dove supportato.
        """
        b64 = base64.b64encode(image_bytes).decode()

        pimeyes_url = "https://pimeyes.com/en"

        return {
            "results": [
                {"url": pimeyes_url, "title": "PimEyes — motore OSINT facciale (upload manuale)", "source": "pimeyes", "note": "Il più potente per ricerca facciale"},
                {"url": "https://www.bing.com/visualsearch", "title": "Bing Visual Search", "source": "bing"},
                {"url": "https://images.google.com", "title": "Google Images", "source": "google"},
            ],
            "note": "Link apertura diretta — carica l'immagine manualmente su queste piattaforme",
        }
