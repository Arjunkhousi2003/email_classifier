from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Category, Email, Rule, User
from app.db.session import get_db
from app.schemas import RuleCreate

router = APIRouter(tags=["categories"])

FIELDS = {"subject", "sender", "body", "any"}
OPERATORS = {"contains", "equals", "regex"}


@router.get("/get-categories")
def get_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    counts = dict(
        db.execute(
            select(Email.category_id, func.count(Email.id))
            .where(Email.user_id == user.id)
            .group_by(Email.category_id)
        ).all()
    )
    categories = []
    for row in db.scalars(select(Category).order_by(Category.name)).all():
        categories.append(
            {
                "slug": row.slug,
                "name": row.name,
                "description": row.description,
                "count": int(counts.get(row.id, 0)),
            }
        )
    return {"categories": categories}


@router.get("/rules")
def list_rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Rule).where((Rule.user_id.is_(None)) | (Rule.user_id == user.id))).all()
    return {
        "rules": [
            {
                "id": str(row.id),
                "category": row.category.slug,
                "field": row.field,
                "operator": row.operator,
                "pattern": row.pattern,
                "priority": row.priority,
                "enabled": row.enabled,
                "scope": "global" if row.user_id is None else "user",
            }
            for row in rows
        ]
    }


@router.post("/rules")
def create_rule(
    body: RuleCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if body.field not in FIELDS or body.operator not in OPERATORS:
        raise HTTPException(status_code=400, detail="Invalid field or operator")
    category = db.scalar(select(Category).where(Category.slug == body.category))
    if category is None:
        raise HTTPException(status_code=400, detail="Unknown category")
    rule = Rule(
        user_id=user.id,
        category_id=category.id,
        field=body.field,
        operator=body.operator,
        pattern=body.pattern,
        priority=body.priority,
        enabled=True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"id": str(rule.id), "category": category.slug}
