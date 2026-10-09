from pathlib import Path

from app.config import normalize_database_url
from app.services.classifier import EmailClassifier
from app.services.rules import RuleSpec, apply_rules

PAYMENT = [
    RuleSpec("spam", "any", "contains", "lottery", 100),
    RuleSpec("payment", "any", "contains", "invoice", 90),
    RuleSpec("promotions", "any", "contains", "unsubscribe", 80),
]


def test_supabase_uri_gets_driver_and_ssl():
    url = normalize_database_url(
        "postgresql://postgres.abc:secret@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
    )
    assert url.startswith("postgresql+psycopg2://")
    assert "sslmode=require" in url


def test_invoice_is_payment():
    result = apply_rules(PAYMENT, "Your invoice is ready", "billing@shop.test", "Amount due")
    assert result is not None
    assert result.category == "payment"
    assert result.source == "rule"


def test_lottery_outranks_sale_language():
    result = apply_rules(PAYMENT, "You have a sale", "prize@spam.test", "Claim your lottery winnings")
    assert result is not None
    assert result.category == "spam"


def test_model_trains_when_rules_do_not_match(tmp_path: Path):
    classifier = EmailClassifier(model_path=str(tmp_path / "classifier.joblib"))
    samples = [
        ("project kickoff notes for monday", "general"),
        ("team standup agenda attached", "general"),
        ("please review the design doc", "general"),
        ("quarterly planning workshop", "general"),
        ("shipment delayed at the dock", "general"),
        ("wire instructions for vendor", "payment"),
        ("card statement closing tomorrow", "payment"),
        ("amount due on account 4412", "payment"),
        ("bank transfer confirmation", "payment"),
    ]
    metrics = classifier.train(samples)
    assert metrics["samples"] == 9
    result = classifier.classify("standup notes for the team", "pm@work.test", "agenda inside", rules=[])
    assert result.source == "ml"
    assert result.category in {"general", "payment"}
