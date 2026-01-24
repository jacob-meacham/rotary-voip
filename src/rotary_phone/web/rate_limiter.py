"""Rate limiting configuration for the web API."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Create a limiter instance using client IP address as the key
limiter = Limiter(key_func=get_remote_address)

# Rate limit constants
LOGIN_RATE_LIMIT = "5/minute"  # 5 login attempts per minute per IP
