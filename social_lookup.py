"""
face_recognition-ng — Social Media Lookup (Fase 3)
Ricerca profili pubblici sui social network dato un nome/username.
Integra i risultati con il riconoscimento facciale.

Fonti supportate:
  - Instagram (profili pubblici)
  - Twitter/X
  - LinkedIn (risultati Google)
  - Facebook
  - TikTok
  - GitHub
  - Maigret (username multi-piattaforma)

Usage:
    lookup = SocialLookup()
    results = await lookup.search_by_name("Mario Rossi")
    results = await lookup.search_by_username("mario_rossi")
"""

import asyncio
import re
from typing import List, Dict, Optional
from urllib.parse import quote_plus

import httpx


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8",
}


class SocialLookup:
    """
    Ricerca profili social pubblici dato un nome o username.
    Usa Google dorks e endpoint pubblici — nessuna API key richiesta.
    """

    PLATFORMS = {
        "instagram": "site:instagram.com",
        "twitter": "site:twitter.com OR site:x.com",
        "linkedin": "site:linkedin.com/in",
        "facebook": "site:facebook.com",
        "tiktok": "site:tiktok.com",
        "github": "site:github.com",
    }

    DIRECT_URLS = {
        "instagram": "https://www.instagram.com/{username}/",
        "twitter": "https://twitter.com/{username}",
        "tiktok": "https://www.tiktok.com/@{username}",
        "github": "https://github.com/{username}",
        "facebook": "https://www.facebook.com/{username}",
    }

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    async def search_by_name(self, name: str) -> Dict:
        """
        Cerca profili social dato un nome completo.
        Usa Google dorks per ogni piattaforma.
        """
        tasks = [
            self._google_dork_search(name, platform, dork)
            for platform, dork in self.PLATFORMS.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {"query": name, "type": "name", "platforms": {}}
        for (platform, _), result in zip(self.PLATFORMS.items(), results):
            if isinstance(result, Exception):
                output["platforms"][platform] = {"error": str(result), "results": []}
            else:
                output["platforms"][platform] = result

        return output

    async def search_by_username(self, username: str) -> Dict:
        """
        Dato un username, verifica la presenza diretta su ogni piattaforma.
        Controlla se il profilo esiste (HTTP 200 = esiste, 404 = non esiste).
        """
        tasks = [
            self._check_profile(platform, url_template.format(username=username), username)
            for platform, url_template in self.DIRECT_URLS.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {"query": username, "type": "username", "found": [], "not_found": [], "platforms": {}}
        for result in results:
            if isinstance(result, Exception):
                continue
            platform = result["platform"]
            output["platforms"][platform] = result
            if result.get("exists"):
                output["found"].append(platform)
            else:
                output["not_found"].append(platform)

        return output

    async def _check_profile(self, platform: str, url: str, username: str) -> Dict:
        """Verifica se un profilo esiste su una piattaforma."""
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(url)
                exists = resp.status_code == 200

                # Heuristics per distinguere profili reali da pagine "non trovato"
                if exists and platform == "instagram":
                    exists = "Page Not Found" not in resp.text and "Sorry, this page" not in resp.text
                elif exists and platform == "twitter":
                    exists = "This account doesn't exist" not in resp.text
                elif exists and platform == "github":
                    exists = "Not Found" not in resp.text

                return {
                    "platform": platform,
                    "url": url,
                    "exists": exists,
                    "status_code": resp.status_code,
                }
        except Exception as e:
            return {"platform": platform, "url": url, "exists": False, "error": str(e)}

    async def _google_dork_search(self, name: str, platform: str, dork: str) -> Dict:
        """Genera link Google dork per la piattaforma."""
        query = f'{dork} "{name}"'
        search_url = f"https://www.google.com/search?q={quote_plus(query)}"
        return {
            "platform": platform,
            "query": query,
            "search_url": search_url,
            "results": [{"url": search_url, "title": f"Cerca '{name}' su {platform.capitalize()}"}],
        }

    def generate_osint_report_links(self, name: str, username: Optional[str] = None) -> List[Dict]:
        """Genera una lista di link OSINT utili per ricerca manuale."""
        q_name = quote_plus(name)
        links = [
            {"label": "Google — immagini", "url": f"https://www.google.com/search?q={q_name}&tbm=isch"},
            {"label": "Google — news", "url": f"https://www.google.com/search?q={q_name}&tbm=nws"},
            {"label": "Bing — persone", "url": f"https://www.bing.com/search?q={q_name}"},
            {"label": "LinkedIn", "url": f"https://www.linkedin.com/search/results/people/?keywords={q_name}"},
            {"label": "Twitter/X", "url": f"https://twitter.com/search?q={q_name}&f=user"},
            {"label": "Facebook", "url": f"https://www.facebook.com/search/people/?q={q_name}"},
            {"label": "TikTok", "url": f"https://www.tiktok.com/search/user?q={q_name}"},
            {"label": "Instagram", "url": f"https://www.instagram.com/explore/tags/{quote_plus(name.replace(' ', ''))}/"},
            {"label": "PimEyes (facciale)", "url": "https://pimeyes.com/en"},
            {"label": "Yandex Images", "url": "https://yandex.com/images/"},
        ]
        if username:
            q_u = quote_plus(username)
            links += [
                {"label": f"Instagram @{username}", "url": f"https://www.instagram.com/{username}/"},
                {"label": f"Twitter @{username}", "url": f"https://twitter.com/{username}"},
                {"label": f"GitHub @{username}", "url": f"https://github.com/{username}"},
                {"label": f"TikTok @{username}", "url": f"https://www.tiktok.com/@{username}"},
            ]
        return links
