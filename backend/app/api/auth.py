from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import create_access_token, create_oauth_state, get_current_user, read_oauth_state
from app.config import get_settings
from app.db.models import Email, ImapAccount, OAuthCredential, Rule, User
from app.db.session import get_db
from app.schemas import DevLoginRequest, ImapConnectRequest, MailboxLoginRequest
from app.services.crypto import encrypt
from app.services.errors import ProviderError
from app.services.gmail import authorization_url, exchange_code, profile_email
from app.services.imap_client import verify_login
from app.services.imap_hosts import normalize_mailbox_password, resolve_imap_host

router = APIRouter(tags=["auth"])


def _user_payload(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "gmail_connected": any(item.provider == "gmail" for item in user.oauth_credentials),
        "imap_accounts": [
            {"host": item.host, "username": item.username, "port": item.port} for item in user.imap_accounts
        ],
    }


@router.get("/auth")
def auth_status(user: User = Depends(get_current_user)) -> dict:
    return _user_payload(user)


@router.post("/auth/dev")
def dev_login(body: DevLoginRequest, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    if not settings.dev_mode:
        raise HTTPException(status_code=404, detail="Not found")
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    if user is None:
        user = User(email=email, name=body.name or email.split("@")[0])
        db.add(user)
        db.commit()
        db.refresh(user)
    return {"access_token": create_access_token(user.id), "token_type": "bearer", "user": _user_payload(user)}


@router.get("/auth/google")
def google_start() -> dict:
    try:
        url = authorization_url(create_oauth_state())
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"authorization_url": url}


@router.get("/auth/google/callback")
def google_callback(code: str, state: str, db: Session = Depends(get_db)) -> RedirectResponse:
    read_oauth_state(state)
    credentials = exchange_code(code)
    address = profile_email(credentials).strip().lower()
    if not address:
        raise HTTPException(status_code=502, detail="Google account has no email address")
    user = db.scalar(select(User).where(User.email == address, User.deleted_at.is_(None)))
    if user is None:
        user = User(email=address, name=address.split("@")[0])
        db.add(user)
        db.flush()
    existing = db.scalar(
        select(OAuthCredential).where(OAuthCredential.user_id == user.id, OAuthCredential.provider == "gmail")
    )
    expiry = credentials.expiry
    if expiry is not None and expiry.tzinfo is None:
        from datetime import timezone

        expiry = expiry.replace(tzinfo=timezone.utc)
    payload = {
        "access_token_enc": encrypt(credentials.token or ""),
        "refresh_token_enc": encrypt(credentials.refresh_token) if credentials.refresh_token else None,
        "token_expiry": expiry,
        "scopes": " ".join(credentials.scopes or []),
    }
    if existing is None:
        db.add(OAuthCredential(user_id=user.id, provider="gmail", **payload))
    else:
        if payload["refresh_token_enc"] is None:
            payload["refresh_token_enc"] = existing.refresh_token_enc
        for key, value in payload.items():
            setattr(existing, key, value)
    db.commit()
    token = create_access_token(user.id)
    target = f"{get_settings().frontend_url}/?{urlencode({'token': token})}"
    return RedirectResponse(target)


def _save_imap_account(
    db: Session,
    user: User,
    host: str,
    username: str,
    password: str,
    port: int,
    use_ssl: bool,
) -> None:
    existing = db.scalar(
        select(ImapAccount).where(
            ImapAccount.user_id == user.id,
            ImapAccount.host == host,
            ImapAccount.username == username,
        )
    )
    password_enc = encrypt(password)
    if existing is None:
        db.add(
            ImapAccount(
                user_id=user.id,
                host=host,
                port=port,
                username=username,
                password_enc=password_enc,
                use_ssl=use_ssl,
            )
        )
    else:
        existing.password_enc = password_enc
        existing.port = port
        existing.use_ssl = use_ssl


@router.post("/auth/mailbox")
def mailbox_login(body: MailboxLoginRequest, db: Session = Depends(get_db)) -> dict:
    """Sign in with the mailbox address and password, then store the verified IMAP account."""
    address = body.email.strip().lower()
    password = normalize_mailbox_password(body.password)
    try:
        host = (body.host or "").strip() or resolve_imap_host(address)
        verify_login(host, address, password, port=body.port, use_ssl=True)
    except ProviderError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = db.scalar(select(User).where(User.email == address, User.deleted_at.is_(None)))
    if user is None:
        user = User(email=address, name=address.split("@")[0])
        db.add(user)
        db.flush()
    _save_imap_account(db, user, host, address, password, body.port, True)
    db.commit()
    db.refresh(user)
    return {"access_token": create_access_token(user.id), "token_type": "bearer", "user": _user_payload(user)}


@router.post("/auth/imap")
def connect_imap(
    body: ImapConnectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    username = body.username.strip()
    password = normalize_mailbox_password(body.password)
    try:
        host = (body.host or "").strip() or resolve_imap_host(username)
        verify_login(host, username, password, port=body.port, use_ssl=body.use_ssl)
    except ProviderError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _save_imap_account(db, user, host, username, password, body.port, body.use_ssl)
    db.commit()
    db.refresh(user)
    return _user_payload(user)


@router.get("/auth/export")
def export_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    emails = db.scalars(select(Email).where(Email.user_id == user.id)).all()
    return {
        "user": {"email": user.email, "name": user.name, "created_at": user.created_at},
        "emails": [
            {
                "sender": row.sender,
                "subject": row.subject,
                "body_text": row.body_text,
                "received_at": row.received_at,
                "category": row.category.slug if row.category else None,
                "classification_source": row.classification_source,
            }
            for row in emails
        ],
    }


@router.delete("/auth/account")
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    from datetime import datetime, timezone

    db.execute(delete(Email).where(Email.user_id == user.id))
    db.execute(delete(Rule).where(Rule.user_id == user.id))
    db.execute(delete(OAuthCredential).where(OAuthCredential.user_id == user.id))
    db.execute(delete(ImapAccount).where(ImapAccount.user_id == user.id))
    user.name = None
    user.email = f"deleted-{user.id}@redacted.invalid"
    user.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"deleted": True}
