"""Persist fetched mail and run the rules-then-model classifier."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Category, ClassificationModel, Email, ImapAccount, OAuthCredential, Rule, User
from app.services.classifier import get_classifier, message_text
from app.services.crypto import decrypt, encrypt
from app.services.errors import ProviderError
from app.services.gmail import fetch_messages as fetch_gmail
from app.services.gmail import profile_email, refresh_if_needed, to_credentials
from app.services.imap_client import fetch_messages as fetch_imap
from app.services.rules import RuleSpec


def load_rules(db: Session, user_id: uuid.UUID) -> list[RuleSpec]:
    rows = db.scalars(
        select(Rule)
        .join(Category)
        .where(Rule.enabled.is_(True), or_(Rule.user_id.is_(None), Rule.user_id == user_id))
    ).all()
    return [
        RuleSpec(
            category=row.category.slug,
            field=row.field,
            operator=row.operator,
            pattern=row.pattern,
            priority=row.priority,
        )
        for row in rows
    ]


def category_map(db: Session) -> dict[str, Category]:
    return {row.slug: row for row in db.scalars(select(Category)).all()}


def upsert_messages(db: Session, user_id: uuid.UUID, messages: list[dict]) -> tuple[int, int]:
    rules = load_rules(db, user_id)
    categories = category_map(db)
    classifier = get_classifier()
    created = 0
    for message in messages:
        existing = db.scalar(
            select(Email).where(
                Email.user_id == user_id,
                Email.provider == message["provider"],
                Email.provider_message_id == message["provider_message_id"],
            )
        )
        if existing is not None:
            continue
        result = classifier.classify(message.get("subject"), message.get("sender"), message.get("body_text"), rules)
        category = categories.get(result.category) or categories["general"]
        db.add(
            Email(
                user_id=user_id,
                provider=message["provider"],
                provider_message_id=message["provider_message_id"],
                thread_id=message.get("thread_id"),
                sender=message.get("sender"),
                recipients=message.get("recipients"),
                subject=message.get("subject"),
                snippet=message.get("snippet"),
                body_text=message.get("body_text"),
                received_at=message.get("received_at"),
                category_id=category.id,
                confidence=result.confidence,
                classification_source=result.source,
                headers=message.get("headers"),
            )
        )
        created += 1
    db.commit()
    return len(messages), created


def classify_emails(db: Session, user_id: uuid.UUID, email_ids: list[uuid.UUID] | None = None) -> int:
    rules = load_rules(db, user_id)
    categories = category_map(db)
    classifier = get_classifier()
    query = select(Email).where(Email.user_id == user_id)
    if email_ids:
        query = query.where(Email.id.in_(email_ids))
    updated = 0
    for row in db.scalars(query).all():
        if row.classification_source == "manual":
            continue
        result = classifier.classify(row.subject, row.sender, row.body_text, rules)
        category = categories.get(result.category) or categories["general"]
        row.category_id = category.id
        row.confidence = result.confidence
        row.classification_source = result.source
        updated += 1
    db.commit()
    return updated


def _gmail_messages(db: Session, credential: OAuthCredential, limit: int) -> list[dict]:
    access = decrypt(credential.access_token_enc)
    refresh = decrypt(credential.refresh_token_enc) if credential.refresh_token_enc else None
    credentials = refresh_if_needed(to_credentials(access, refresh, credential.token_expiry))
    if credentials.token and credentials.token != access:
        credential.access_token_enc = encrypt(credentials.token)
        credential.token_expiry = (
            credentials.expiry.replace(tzinfo=timezone.utc) if credentials.expiry is not None else None
        )
        credential.updated_at = datetime.now(timezone.utc)
        db.commit()
    return fetch_gmail(credentials, limit=limit)


def gmail_identity(db: Session, credential: OAuthCredential) -> str:
    access = decrypt(credential.access_token_enc)
    refresh = decrypt(credential.refresh_token_enc) if credential.refresh_token_enc else None
    credentials = refresh_if_needed(to_credentials(access, refresh, credential.token_expiry))
    return profile_email(credentials)


def sync_user(db: Session, user: User, limit: int = 25) -> dict:
    fetched = 0
    created = 0
    errors: list[str] = []
    for credential in user.oauth_credentials:
        if credential.provider != "gmail":
            continue
        try:
            messages = _gmail_messages(db, credential, limit)
            seen, new = upsert_messages(db, user.id, messages)
            fetched += seen
            created += new
        except (ProviderError, ValueError) as exc:
            errors.append(str(exc))
    for account in user.imap_accounts:
        try:
            messages = fetch_imap(
                host=account.host,
                username=account.username,
                password=decrypt(account.password_enc),
                port=account.port,
                use_ssl=account.use_ssl,
                limit=limit,
            )
            seen, new = upsert_messages(db, user.id, messages)
            fetched += seen
            created += new
        except (ProviderError, ValueError) as exc:
            errors.append(str(exc))
    return {"fetched": fetched, "created": created, "errors": errors}


def train_from_labels(db: Session, user_id: uuid.UUID) -> dict:
    rows = db.scalars(select(Email).where(Email.user_id == user_id, Email.category_id.is_not(None))).all()
    samples = []
    for row in rows:
        if row.category is None:
            continue
        text = message_text(row.subject, row.sender, row.body_text)
        if text:
            samples.append((text, row.category.slug))
    metrics = get_classifier().train(samples)
    db.execute(update(ClassificationModel).values(is_active=False))
    db.add(
        ClassificationModel(
            version=metrics["trained_at"],
            artifact_path=str(get_classifier().model_path),
            metrics=metrics,
            is_active=True,
        )
    )
    db.commit()
    return metrics


def purge_expired(db: Session) -> int:
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_days)
    rows = db.scalars(select(Email).where(Email.received_at.is_not(None), Email.received_at < cutoff)).all()
    count = len(rows)
    for row in rows:
        db.delete(row)
    db.commit()
    return count
