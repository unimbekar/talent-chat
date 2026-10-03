"""Google Workspace sign-in for recruiters.

The same consent that proves the person works at Janus Soft also grants
read-only access to the Drive folders they can already open. CloudFormation
cannot create the Google OAuth client. It stores the client id and secret.
"""

from urllib.parse import urlencode

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN = "https://oauth2.googleapis.com/token"
_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
_SCOPE = "openid email profile https://www.googleapis.com/auth/drive.readonly"


class GoogleSignInError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def google_configured() -> bool:
    settings = get_settings()
    return bool(settings.google_client_id.strip() and settings.google_client_secret.strip())


def redirect_uri() -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/api/admin/login/google/callback"


def sign_state() -> str:
    return _state_serializer().dumps({"ok": 1})


def authorization_url(state: str) -> str:
    settings = get_settings()
    query = urlencode(
        {
            "client_id": settings.google_client_id.strip(),
            "redirect_uri": redirect_uri(),
            "response_type": "code",
            "scope": _SCOPE,
            "state": state,
            "hd": settings.company_email_domain.strip().lower(),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
    )
    return f"{_AUTH}?{query}"


def exchange_code(code: str, state: str) -> tuple[str, str]:
    """Return (email, refresh token). Raises GoogleSignInError."""
    if not _valid_state(state):
        raise GoogleSignInError("state")
    settings = get_settings()
    try:
        response = httpx.post(
            _TOKEN,
            data={
                "code": code,
                "client_id": settings.google_client_id.strip(),
                "client_secret": settings.google_client_secret.strip(),
                "redirect_uri": redirect_uri(),
                "grant_type": "authorization_code",
            },
            timeout=20,
        )
        response.raise_for_status()
        token = response.json()
        info = httpx.get(_TOKENINFO, params={"id_token": token.get("id_token", "")}, timeout=20)
        info.raise_for_status()
        claims = info.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GoogleSignInError("google") from exc
    verified = str(claims.get("email_verified", "")).lower() == "true"
    if not workspace_account(
        str(claims.get("email") or ""),
        str(claims.get("hd") or ""),
        email_verified=verified,
        allowed=settings.company_email_domain,
    ):
        raise GoogleSignInError("domain")
    return str(claims["email"]).strip().lower(), str(token.get("refresh_token") or "")


def access_token(refresh_token: str) -> str:
    settings = get_settings()
    try:
        response = httpx.post(
            _TOKEN,
            data={
                "client_id": settings.google_client_id.strip(),
                "client_secret": settings.google_client_secret.strip(),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=20,
        )
        response.raise_for_status()
        token = response.json().get("access_token") or ""
    except (httpx.HTTPError, ValueError) as exc:
        raise GoogleSignInError("google") from exc
    if not token:
        raise GoogleSignInError("google")
    return token


def workspace_account(email: str, hosted_domain: str, *, email_verified: bool, allowed: str) -> bool:
    """True for a verified address at the company domain. Consumer Gmail stays out."""
    if not email_verified:
        return False
    domain = allowed.strip().lower()
    address = email.strip().lower()
    if not domain or "@" not in address or not address.endswith("@" + domain):
        return False
    hosted = hosted_domain.strip().lower()
    return not hosted or hosted == domain


def _state_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt="google-login")


def _valid_state(state: str) -> bool:
    if not state:
        return False
    try:
        _state_serializer().loads(state, max_age=600)
    except (BadSignature, SignatureExpired):
        return False
    return True
