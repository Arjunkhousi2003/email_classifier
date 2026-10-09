import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.models import Category, Email, User
from app.db.session import get_db
from app.schemas import CategoryUpdate, FetchRequest, FilterRequest, ImportRequest
from app.services.errors import ProviderError
from app.services.sync import classify_emails, sync_user, train_from_labels, upsert_messages

router = APIRouter(tags=["emails"])


def _email_dict(row: Email) -> dict:
    return {
        "id": str(row.id),
        "provider": row.provider,
        "sender": row.sender,
        "subject": row.subject,
        "snippet": row.snippet,
        "body_text": row.body_text,
        "received_at": row.received_at,
        "category": row.category.slug if row.category else "general",
        "confidence": row.confidence,
        "classification_source": row.classification_source,
    }


@router.post("/fetch-emails")
def fetch_emails(
    body: FetchRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    limit = body.limit if body else 25
    try:
        return sync_user(db, user, limit=limit)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/filter-emails")
def filter_emails(
    body: FilterRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    email_ids = body.email_ids if body else None
    updated = classify_emails(db, user.id, email_ids)
    return {"updated": updated}


@router.post("/filter-emails/train")
def train_model(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        return train_from_labels(db, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/emails")
def list_emails(
    category: str | None = None,
    q: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    query = select(Email).where(Email.user_id == user.id).options(selectinload(Email.category))
    if category:
        query = query.join(Category).where(Category.slug == category)
    if q:
        like = f"%{q}%"
        query = query.where(or_(Email.subject.ilike(like), Email.sender.ilike(like), Email.snippet.ilike(like)))
    rows = db.scalars(
        query.order_by(Email.received_at.desc().nulls_last(), Email.created_at.desc()).limit(min(limit, 200))
    ).all()
    return {"emails": [_email_dict(row) for row in rows]}


@router.patch("/emails/{email_id}")
def relabel_email(
    email_id: uuid.UUID,
    body: CategoryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = db.scalar(
        select(Email).where(Email.id == email_id, Email.user_id == user.id).options(selectinload(Email.category))
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Email not found")
    category = db.scalar(select(Category).where(Category.slug == body.category))
    if category is None:
        raise HTTPException(status_code=400, detail="Unknown category")
    row.category_id = category.id
    row.classification_source = "manual"
    row.confidence = 1.0
    db.commit()
    db.refresh(row)
    row.category = category
    return _email_dict(row)


@router.post("/emails/import")
def import_messages(
    body: ImportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    messages = []
    now = datetime.now(timezone.utc)
    for item in body.messages:
        messages.append(
            {
                "provider": "import",
                "provider_message_id": str(uuid.uuid4()),
                "thread_id": None,
                "sender": item.sender[:500],
                "recipients": user.email,
                "subject": item.subject,
                "snippet": (item.body or item.subject)[:180],
                "body_text": (item.body or "")[:20000],
                "received_at": item.received_at or now,
                "headers": {"from": item.sender, "subject": item.subject},
            }
        )
    fetched, created = upsert_messages(db, user.id, messages)
    return {"fetched": fetched, "created": created}
