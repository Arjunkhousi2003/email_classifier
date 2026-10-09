from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Category, Rule

CATEGORIES = [
    ("payment", "Payment", "Invoices, receipts, and billing notices"),
    ("spam", "Spam", "Unsolicited or deceptive mail"),
    ("promotions", "Promotions", "Marketing and sales offers"),
    ("general", "General", "Mail that does not match another category"),
]

# Higher priority wins. Spam is checked before payment and promotions.
GLOBAL_RULES = [
    ("spam", "any", "contains", "lottery", 100),
    ("spam", "any", "contains", "you have won", 100),
    ("spam", "any", "contains", "wire transfer", 95),
    ("spam", "any", "contains", "verify your account immediately", 95),
    ("payment", "any", "contains", "invoice", 90),
    ("payment", "any", "contains", "receipt", 90),
    ("payment", "any", "contains", "payment", 85),
    ("payment", "sender", "contains", "billing@", 88),
    ("promotions", "any", "contains", "unsubscribe", 80),
    ("promotions", "any", "contains", "% off", 80),
    ("promotions", "any", "contains", "limited time", 75),
    ("promotions", "any", "contains", "sale", 70),
]


def seed(db: Session) -> None:
    existing = {row.slug: row for row in db.scalars(select(Category)).all()}
    for slug, name, description in CATEGORIES:
        if slug not in existing:
            db.add(Category(slug=slug, name=name, description=description))
    db.flush()
    by_slug = {row.slug: row for row in db.scalars(select(Category)).all()}

    current = {
        (rule.field, rule.operator, rule.pattern, rule.category.slug)
        for rule in db.scalars(select(Rule).where(Rule.user_id.is_(None))).all()
    }
    for slug, field, operator, pattern, priority in GLOBAL_RULES:
        key = (field, operator, pattern, slug)
        if key in current:
            continue
        db.add(
            Rule(
                user_id=None,
                category_id=by_slug[slug].id,
                field=field,
                operator=operator,
                pattern=pattern,
                priority=priority,
                enabled=True,
            )
        )
    db.commit()
