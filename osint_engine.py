"""
face_recognition-ng — OSINT Engine (Fase 3)
Ricerca reverse image su più fonti:
  - Google Lens (via upload)
  - Yandex Images
  - TinEye
  - Link statici (PimEyes, Bing, Google Images)

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
import re
from typing import List, Dict, Optional
from dataclasses import dataclass, field

import httpx
from PIL import Image


OSINT_ENABLE_EXTERNAL = os.getenv("OSINT_ENABLE_EXTERNAL", "true").lower() == "true"
# 6s per singola fonte, 18s globale (abbondante sotto il 24s cutoff di Railway)
OSINT_TIMEOUT = int(os.getenv("OSINT_TIMEOUT", "6"))
OSINT_GLOBAL_TIMEOUT = int(os.getenv("OSINT_GLOBAL_TIMEOUT", "18"))
# Dimensione massima lato immagine prima dell'upload (px)
OSINT_MAX_IMAGE_PX = int(os.getenv("OSINT_MAX_IMAGE_PX", "800"))
OSINT_JPEG_QUALITY = int(os.getenv("OSINT_JPEG_QUALITY", "82"))


@dataclass
class OsintResult:
    source: str
    url: str
    title: str = ""
    thumbnail: str = ""
    confidence: float = 0.0
    extra: Dict = field(default_factory=dict)


def _resize_image(image_bytes: bytes, max_px: int = OSINT_MAX_IMAGE_PX, quality: int = OSINT_JPEG_QUALITY) -> bytes:
    """
    Ridimensiona l'immagine a max_px sul lato lungo e ricodifica in JPEG.
    Riduce il payload da ~700KB a ~50-80KB, accelerando enormemente i POST.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        if max(w, h) > max_px:
            scale = max_px / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    except Exception:
        # Se resize fallisce usa l'originale
        return image_bytes


class OsintEngine:
    """
    Motore OSINT per reverse image search su più fonti.
    Usa solo endpoint pubblici — nessuna API key richiesta.

    ENV:
    - OSINT_ENABLE_EXTERNAL=false  disabilita chiamate esterne
    - OSINT_TIMEOUT=6              timeout per singola fonte (s)
    - OSINT_GLOBAL_TIMEOUT=18      timeout totale gather (s)
    - OSINT_MAX_IMAGE_PX=800       resize immagine prima upload
    - OSINT_JPEG_QUALITY=82        qualita JPEG dopo resize
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8",
    }

    def __init__(self, timeout: Optional[int] = None):
        self.timeout = timeout if timeout is not None else OSINT_TIMEOUT

    async def search(self, image_bytes: bytes) -> Dict:
        img_hash = hashlib.md5(image_bytes).hexdigest()[:8]
        # Resize prima di tutto
        small_bytes = _resize_image(image_bytes)

        if not OSINT_ENABLE_EXTERNAL:
            links = await self._build_search_links()
            return {
                "image_hash": img_hash,
                "timestamp": int(time.time()),
                "sources": {"search_links": links},
                "total_results": len(links.get("results", [])),
                "external_calls": False,
            }

        try:
            result = await asyncio.wait_for(
                self._gather_sources(small_bytes, img_hash),
                timeout=OSINT_GLOBAL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            links = await self._build_search_links()
            result = {
                "image_hash": img_hash,
                "timestamp": int(time.time()),
                "sources": {
                    "google_lens": {"results": [], "error": "timeout"},
                    "yandex":      {"results": [], "error": "timeout"},
                    "tineye":      {"results": [], "error": "timeout"},
                    "search_links": links,
                },
                "total_results": len(links.get("results", [])),
                "external_calls": True,
                "timed_out": True,
            }
        return result

    async def _gather_sources(self, small_bytes: bytes, img_hash: str) -> Dict:
        tasks = [
            self._search_google_lens(small_bytes),
            self._search_yandex(small_bytes),
            self._search_tineye(small_bytes),
            self._build_search_links(),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        output = {
            "image_hash": img_hash,
            "timestamp": int(time.time()),
            "sources": {},
            "total_results": 0,
            "external_calls": True,
        }
        for name, result in zip(["google_lens", "yandex", "tineye", "search_links"], results):
            if isinstance(result, Exception):
                output["sources"][name] = {"error": str(result), "results": []}
            else:
                output["sources"][name] = result
                output["total_results"] += len(result.get("results", []))
        return output

    async def _search_google_lens(self, image_bytes: bytes) -> Dict:
        """
        Google Lens: POST immagine, NON seguire i redirect.
        L'URL del redirect 302 e' gia' il link di ricerca visiva.
        """
        try:
            async with httpx.AsyncClient(
                headers=self.HEADERS,
                timeout=self.timeout,
                follow_redirects=False,  # vogliamo solo l'URL del redirect
            ) as client:
                files = {"encoded_image": ("face.jpg", image_bytes, "image/jpeg")}
                resp = await client.post(
                    "https://lens.google.com/upload",
                    files=files,
                    params={"ep": "ccm", "re": "df", "s": "4", "st": str(int(time.time() * 1000))},
                )
                # Location header = URL risultati Lens
                lens_url = resp.headers.get("location") or str(resp.url)
                return {
                    "results": [{"url": lens_url, "title": "Google Lens — apri per risultati visivi", "source": "google_lens"}],
                    "search_url": lens_url,
                }
        except Exception as e:
            return {"results": [], "error": str(e)}

    async def _search_yandex(self, image_bytes: bytes) -> Dict:
        """
        Yandex: POST immagine, NON seguire redirect.
        """
        try:
            async with httpx.AsyncClient(
                headers=self.HEADERS,
                timeout=self.timeout,
                follow_redirects=False,
            ) as client:
                files = {"upfile": ("face.jpg", image_bytes, "image/jpeg")}
                resp = await client.post(
                    "https://yandex.com/images/search",
                    files=files,
                    params={"rpt": "imageview", "format": "json"},
                )
                search_url = resp.headers.get("location") or str(resp.url)
                return {
                    "results": [{"url": search_url, "title": "Yandex Images — apri per risultati", "source": "yandex"}],
                    "search_url": search_url,
                }
        except Exception as e:
            return {"results": [], "error": str(e)}

    async def _search_tineye(self, image_bytes: bytes) -> Dict:
        try:
            async with httpx.AsyncClient(
                headers=self.HEADERS,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                files = {"image": ("face.jpg", image_bytes, "image/jpeg")}
                resp = await client.post("https://tineye.com/search", files=files)
                search_url = str(resp.url)
                count_text = ""
                try:
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

    async def _build_search_links(self) -> Dict:
        return {
            "results": [
                {"url": "https://pimeyes.com/en", "title": "PimEyes — motore OSINT facciale (upload manuale)", "source": "pimeyes"},
                {"url": "https://www.bing.com/visualsearch", "title": "Bing Visual Search", "source": "bing"},
                {"url": "https://images.google.com", "title": "Google Images", "source": "google"},
            ],
            "note": "Link apertura diretta — carica l'immagine manualmente",
        }
