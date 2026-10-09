"""Gmail API client using OAuth 2.0 and the gmail.readonly scope."""

import base64
import os
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.config import get_settings
from app.services.errors import ProviderError

# Google sometimes returns a broader scope set than requested.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
if get_settings().dev_mode:
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

BODY_LIMIT = 20_000


def _client_config() -> dict:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise ProviderError("Google OAuth client is not configured")
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }


def authorization_url(state: str) -> str:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=get_settings().gmail_scopes.split(),
        redirect_uri=get_settings().google_redirect_uri,
    )
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return url


def exchange_code(code: str) -> Credentials:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=get_settings().gmail_scopes.split(),
        redirect_uri=get_settings().google_redirect_uri,
    )
    flow.fetch_token(code=code)
    return flow.credentials


def to_credentials(
    access_token: str,
    refresh_token: str | None,
    expiry: datetime | None,
) -> Credentials:
    settings = get_settings()
    return Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=settings.gmail_scopes.split(),
        expiry=expiry.replace(tzinfo=None) if expiry is not None else None,
    )


def refresh_if_needed(credentials: Credentials) -> Credentials:
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    return credentials


def _decode_data(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="replace")


def _plain_text(payload: dict) -> str:
    chunks: list[str] = []

    def walk(part: dict) -> None:
        body = part.get("body", {})
        if part.get("mimeType") == "text/plain" and body.get("data"):
            chunks.append(_decode_data(body["data"]))
        for child in part.get("parts") or []:
            walk(child)

    walk(payload)
    return "\n".join(chunks)[:BODY_LIMIT]


def _header(headers: list[dict], name: str) -> str:
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def profile_email(credentials: Credentials) -> str:
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    return profile.get("emailAddress", "")


def fetch_messages(credentials: Credentials, limit: int = 25) -> list[dict]:
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    listed = (
        service.users()
        .messages()
        .list(userId="me", maxResults=max(1, min(limit, 100)), q="newer_than:30d")
        .execute()
    )
    messages = []
    for item in listed.get("messages", []):
        full = (
            service.users()
            .messages()
            .get(userId="me", id=item["id"], format="full")
            .execute()
        )
        payload = full.get("payload", {})
        headers = payload.get("headers", [])
        internal_ms = int(full.get("internalDate", "0"))
        received = datetime.fromtimestamp(internal_ms / 1000, tz=timezone.utc) if internal_ms else None
        body = _plain_text(payload)
        subject = _header(headers, "Subject")
        messages.append(
            {
                "provider": "gmail",
                "provider_message_id": full["id"],
                "thread_id": full.get("threadId"),
                "sender": _header(headers, "From")[:500],
                "recipients": _header(headers, "To"),
                "subject": subject,
                "snippet": (full.get("snippet") or body[:180])[:500],
                "body_text": body,
                "received_at": received,
                "headers": {
                    "from": _header(headers, "From"),
                    "to": _header(headers, "To"),
                    "subject": subject,
                    "date": _header(headers, "Date"),
                },
            }
        )
    return messages
