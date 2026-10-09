"""Periodic inbox sync and retention."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import User
from app.db.session import SessionLocal
from app.services.sync import purge_expired, sync_user
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.sync_all_users")
def sync_all_users() -> dict:
    db = SessionLocal()
    synced = 0
    try:
        user_ids = list(db.scalars(select(User.id).where(User.deleted_at.is_(None))).all())
        for user_id in user_ids:
            user = db.scalar(
                select(User)
                .where(User.id == user_id)
                .options(selectinload(User.oauth_credentials), selectinload(User.imap_accounts))
            )
            if user is None:
                continue
            if not user.oauth_credentials and not user.imap_accounts:
                continue
            result = sync_user(db, user)
            logger.info("Synced %s fetched=%s created=%s", user.email, result["fetched"], result["created"])
            synced += 1
        return {"users": synced}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.purge_old_mail")
def purge_old_mail() -> dict:
    db = SessionLocal()
    try:
        removed = purge_expired(db)
        return {"removed": removed}
    finally:
        db.close()
