"""
Clerk JWT verification + FastAPI dependencies.
AUTH_DISABLED=true bypasses all verification (use for local dev).
"""
import logging
from typing import Optional
from fastapi import Request, HTTPException, Header
from config import settings

logger = logging.getLogger(__name__)

ANON_USER = {"id": "anonymous", "email": "anon@alphalens.ai", "name": "Guest"}


async def _verify_clerk_token(token: str) -> dict:
    """Decode and verify a Clerk JWT. Returns user payload."""
    try:
        import jwt
        from jwt import PyJWKClient

        # Clerk JWKS URL derived from publishable key domain
        pk = settings.CLERK_PUBLISHABLE_KEY or ""
        # pk_test_xxx.xxx → frontend API domain
        domain = pk.split("_")[2] if "_" in pk else ""
        jwks_url = f"https://{domain}/.well-known/jwks.json"

        jwks_client = PyJWKClient(jwks_url, cache_keys=True)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return {
            "id": payload.get("sub", ""),
            "email": payload.get("email", ""),
            "name": payload.get("name", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    FastAPI dependency — required auth.
    Returns user dict or 401.
    """
    if settings.AUTH_DISABLED:
        return ANON_USER
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization[len("Bearer "):]
    return await _verify_clerk_token(token)


async def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """
    FastAPI dependency — optional auth.
    Returns user dict if logged in, None if anonymous.
    """
    if settings.AUTH_DISABLED:
        return ANON_USER
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        token = authorization[len("Bearer "):]
        return await _verify_clerk_token(token)
    except Exception:
        return None
