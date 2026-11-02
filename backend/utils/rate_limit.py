"""
Shared rate limiter used across API routes.

A single Limiter instance is created here and attached to the FastAPI app
(`app.state.limiter`) so every route decorator uses the same backend.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
