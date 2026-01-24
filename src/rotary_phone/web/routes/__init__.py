"""Route modules for the web admin interface."""

from rotary_phone.web.routes.allowlist import router as allowlist_router
from rotary_phone.web.routes.auth import router as auth_router
from rotary_phone.web.routes.calls import router as calls_router
from rotary_phone.web.routes.logs import router as logs_router
from rotary_phone.web.routes.network import router as network_router
from rotary_phone.web.routes.settings import router as settings_router
from rotary_phone.web.routes.sounds import router as sounds_router
from rotary_phone.web.routes.speed_dial import router as speed_dial_router

__all__ = [
    "allowlist_router",
    "auth_router",
    "calls_router",
    "logs_router",
    "network_router",
    "settings_router",
    "sounds_router",
    "speed_dial_router",
]
