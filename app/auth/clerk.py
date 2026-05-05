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


async def _fetch_clerk_user(user_id: str) -> dict:
    """Enrich JWT claims that Clerk omits by calling the Clerk REST API."""
    secret = settings.CLERK_SECRET_KEY
    if not secret or not user_id:
        return {}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"https://api.clerk.com/v1/users/{user_id}",
                headers={"Authorization": f"Bearer {secret}"},
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.debug(f"[clerk] API fetch failed for {user_id}: {e}")
    return {}


async def _verify_clerk_token(token: str) -> dict:
    """Decode and verify a Clerk JWT. Returns user payload."""
    try:
        import base64
        import jwt
        from jwt import PyJWKClient

        # Clerk JWKS URL: publishable key format is pk_test_<base64(domain$)>
        # e.g. pk_test_cHJlc2VudC1uZXd0LTkuY2xlcmsuYWNjb3VudHMuZGV2JA
        # → base64 decode → "present-newt-9.clerk.accounts.dev$"
        pk = settings.CLERK_PUBLISHABLE_KEY or ""
        parts = pk.split("_", 2)  # ["pk", "test"|"live", "<base64>"]
        if len(parts) == 3:
            encoded = parts[2]
            # Add padding so len is a multiple of 4
            padded = encoded + "=" * ((4 - len(encoded) % 4) % 4)
            domain = base64.b64decode(padded).decode("utf-8").rstrip("$")
        else:
            domain = ""
        jwks_url = f"https://{domain}/.well-known/jwks.json"

        jwks_client = PyJWKClient(jwks_url, cache_keys=True)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        full_name = (payload.get("name") or "").strip()
        first = payload.get("given_name") or (full_name.split(" ", 1)[0] if full_name else "")
        last  = payload.get("family_name") or (full_name.split(" ", 1)[1] if " " in full_name else "")
        data = {
            "id":         payload.get("sub", ""),
            "email":      payload.get("email", ""),
            "name":       full_name,
            "first_name": first,
            "last_name":  last,
            "image_url":  payload.get("picture") or payload.get("image_url") or "",
        }
        # JWT often lacks email/name; fall back to Clerk REST API to enrich
        if not data["email"] or not data["name"]:
            enriched = await _fetch_clerk_user(data["id"])
            if enriched:
                if not data["email"]:
                    emails = enriched.get("email_addresses", [])
                    pid    = enriched.get("primary_email_address_id", "")
                    data["email"] = next(
                        (e["email_address"] for e in emails if e.get("id") == pid),
                        emails[0]["email_address"] if emails else "",
                    )
                if not data["first_name"]:
                    data["first_name"] = enriched.get("first_name", "")
                if not data["last_name"]:
                    data["last_name"] = enriched.get("last_name", "")
                if not data["name"]:
                    data["name"] = f"{data['first_name']} {data['last_name']}".strip()
                if not data["image_url"]:
                    data["image_url"] = enriched.get("image_url", "")
        return data
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
