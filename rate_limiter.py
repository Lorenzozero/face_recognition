"""
face_recognition-ng — Rate Limiter (in-memory, zero dipendenze esterne)

Implementa fixed-window rate limiting per IP o token.
Backend: dizionario in memoria (thread-safe con Lock).
Per deployment distribuito sostituire _store con Redis.

Variabili ENV:
  RATE_LIMIT_OSINT_IMAGE   (default: 3)   richieste max per finestra
  RATE_LIMIT_OSINT_FULL    (default: 2)
  RATE_LIMIT_OSINT_SOCIAL  (default: 10)
  RATE_LIMIT_OSINT_STATS   (default: 20)
  RATE_LIMIT_WINDOW_SECS   (default: 60)  durata finestra in secondi
  RATE_LIMIT_ENABLED       (default: true) disabilita per test/dev

Usage:
  from rate_limiter import RateLimiter
  limiter = RateLimiter()
  # come FastAPI dependency:
  def route(request: Request, _=Depends(limiter.dep(limit=3))):
      ...
"""

import os
import time
import threading
from typing import Callable
from fastapi import Request, HTTPException, status

RATE_LIMIT_WINDOW_SECS = int(os.environ.get("RATE_LIMIT_WINDOW_SECS", "60"))
RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() != "false"

LIMIT_OSINT_IMAGE = int(os.environ.get("RATE_LIMIT_OSINT_IMAGE", "3"))
LIMIT_OSINT_FULL = int(os.environ.get("RATE_LIMIT_OSINT_FULL", "2"))
LIMIT_OSINT_SOCIAL = int(os.environ.get("RATE_LIMIT_OSINT_SOCIAL", "10"))
LIMIT_OSINT_STATS = int(os.environ.get("RATE_LIMIT_OSINT_STATS", "20"))


class RateLimiter:
    """
    Fixed-window rate limiter in-memory.
    Chiave: <ip>:<route_tag>, finestra: RATE_LIMIT_WINDOW_SECS.
    """

    def __init__(self):
        self._store: dict = {}  # {key: (count, window_start)}
        self._lock = threading.Lock()

    def _client_key(self, request: Request, tag: str) -> str:
        ip = request.client.host if request.client else "unknown"
        # Rispetta X-Forwarded-For se presente (proxy/nginx)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        return f"{ip}:{tag}"

    def check(self, request: Request, tag: str, limit: int) -> dict:
        """
        Controlla il limite. Restituisce dict con headers da aggiungere.
        Solleva HTTP 429 se superato.
        """
        if not RATE_LIMIT_ENABLED:
            return {"X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": str(limit)}

        key = self._client_key(request, tag)
        now = time.time()

        with self._lock:
            entry = self._store.get(key)
            if entry is None or now - entry[1] >= RATE_LIMIT_WINDOW_SECS:
                # Nuova finestra
                self._store[key] = (1, now)
                count = 1
                window_start = now
            else:
                count, window_start = entry
                count += 1
                self._store[key] = (count, window_start)

        remaining = max(0, limit - count)
        reset_in = int(RATE_LIMIT_WINDOW_SECS - (now - window_start))

        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit superato: max {limit} richieste ogni {RATE_LIMIT_WINDOW_SECS}s. Riprova tra {reset_in}s.",
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(reset_in),
                },
            )

        return {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_in),
        }

    def dep(self, limit: int, tag: str = "default") -> Callable:
        """Restituisce una FastAPI dependency con il limite specificato."""
        def _dependency(request: Request):
            self.check(request, tag=tag, limit=limit)
        return _dependency

    def cleanup_expired(self):
        """Rimuove finestre scadute (opzionale, chiama periodicamente)."""
        now = time.time()
        with self._lock:
            expired = [k for k, (_, ws) in self._store.items() if now - ws >= RATE_LIMIT_WINDOW_SECS]
            for k in expired:
                del self._store[k]
