import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app.config import get_settings
from app.services.rules import Classification, RuleSpec, apply_rules, message_text

logger = logging.getLogger(__name__)

GENERAL = "general"


class EmailClassifier:
    """Keyword rules first, then a persisted TF-IDF + logistic regression model."""

    def __init__(self, model_path: str | None = None) -> None:
        settings = get_settings()
        self.model_path = Path(model_path or settings.model_path)
        self.pipeline: Pipeline | None = None
        self._load()

    def _load(self) -> None:
        if self.model_path.exists():
            self.pipeline = joblib.load(self.model_path)
            logger.info("Loaded classifier from %s", self.model_path)

    def classify(
        self,
        subject: str | None,
        sender: str | None,
        body: str | None,
        rules: list[RuleSpec],
    ) -> Classification:
        ruled = apply_rules(rules, subject, sender, body)
        if ruled is not None:
            return ruled
        text = message_text(subject, sender, body)
        if self.pipeline is not None and text:
            labels = self.pipeline.predict([text])
            label = str(labels[0])
            confidence = 0.5
            if hasattr(self.pipeline, "predict_proba"):
                probabilities = self.pipeline.predict_proba([text])[0]
                confidence = float(max(probabilities))
            return Classification(category=label, confidence=confidence, source="ml")
        return Classification(category=GENERAL, confidence=0.34, source="default")

    def train(self, samples: list[tuple[str, str]]) -> dict:
        if len(samples) < 8:
            raise ValueError("Train the model with at least 8 labeled messages")
        texts, labels = zip(*samples, strict=True)
        unique = sorted(set(labels))
        if len(unique) < 2:
            raise ValueError("Training data must include at least two categories")

        pipeline = Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(
                        ngram_range=(1, 2),
                        min_df=1,
                        max_features=20000,
                        stop_words="english",
                    ),
                ),
                ("clf", LogisticRegression(max_iter=400)),
            ]
        )
        pipeline.fit(list(texts), list(labels))
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipeline, self.model_path)
        self.pipeline = pipeline
        metrics = {
            "samples": len(samples),
            "labels": unique,
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }
        self.model_path.with_suffix(".json").write_text(json.dumps(metrics), encoding="utf-8")
        return metrics


_classifier: EmailClassifier | None = None


def get_classifier() -> EmailClassifier:
    global _classifier
    if _classifier is None:
        _classifier = EmailClassifier()
    return _classifier
