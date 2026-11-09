"""Review sentiment scoring using a weighted keyword lexicon."""

import re
from typing import Dict, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.review.models import Review


class SentimentAnalysisService:
    """Analyze sentiment of customer reviews"""

    # Hand-rolled lexicon (not derived from or a subset of VADER's actual word list)
    POSITIVE_WORDS = {
        "excellent": 3,
        "amazing": 3,
        "great": 2,
        "good": 2,
        "wonderful": 3,
        "fantastic": 3,
        "love": 2,
        "best": 3,
        "perfect": 3,
        "happy": 2,
        "satisfied": 2,
        "recommend": 2,
        "professional": 2,
        "quality": 2,
        "fast": 1,
        "clean": 1,
        "friendly": 2,
        "helpful": 2,
    }

    NEGATIVE_WORDS = {
        "terrible": -3,
        "awful": -3,
        "bad": -2,
        "poor": -2,
        "worst": -3,
        "hate": -3,
        "horrible": -3,
        "disappointing": -2,
        "disappointed": -2,
        "unhappy": -2,
        "unsatisfied": -2,
        "slow": -1,
        "dirty": -2,
        "rude": -2,
        "unprofessional": -2,
        "late": -1,
        "never": -1,
        "not": -1,
    }

    def __init__(self, session: AsyncSession):
        self.session = session

    def analyze_text(self, text: str) -> Dict:
        """
        Analyze sentiment of text
        Returns: compound score (-1 to 1), positive/negative/neutral scores
        """
        if not text:
            return {"compound": 0, "positive": 0, "negative": 0, "neutral": 1.0, "sentiment": "neutral"}

        text_lower = text.lower()
        words = re.findall(r"\b\w+\b", text_lower)

        positive_score = 0
        negative_score = 0

        for word in words:
            if word in self.POSITIVE_WORDS:
                positive_score += self.POSITIVE_WORDS[word]
            elif word in self.NEGATIVE_WORDS:
                negative_score += abs(self.NEGATIVE_WORDS[word])

        total = positive_score + negative_score
        if total == 0:
            return {"compound": 0, "positive": 0, "negative": 0, "neutral": 1.0, "sentiment": "neutral"}

        # Normalize scores
        pos_norm = positive_score / total
        neg_norm = negative_score / total

        # Compound score (-1 to 1)
        compound = (positive_score - negative_score) / max(total, 1)
        compound = max(-1, min(1, compound))  # Clamp to [-1, 1]

        # Classify sentiment
        if compound >= 0.05:
            sentiment = "positive"
        elif compound <= -0.05:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        return {
            "compound": round(compound, 3),
            "positive": round(pos_norm, 3),
            "negative": round(neg_norm, 3),
            "neutral": round(1 - pos_norm - neg_norm, 3),
            "sentiment": sentiment,
        }

    async def analyze_review(self, review_id: UUID) -> Dict:
        """Analyze sentiment of a specific review"""
        result = await self.session.execute(select(Review).where(Review.id == review_id))
        review = result.scalar_one_or_none()

        if not review:
            return {"error": "Review not found"}

        sentiment = self.analyze_text(review.comment)

        return {
            "review_id": str(review_id),
            "rating": review.rating,
            "sentiment": sentiment,
            "rating_sentiment_match": (review.rating >= 4 and sentiment["sentiment"] == "positive")
            or (review.rating <= 2 and sentiment["sentiment"] == "negative"),
        }

    async def analyze_provider_sentiment(self, provider_id: UUID) -> Dict:
        """Analyze overall sentiment for a provider's reviews"""
        result = await self.session.execute(select(Review).where(Review.provider_id == provider_id))
        reviews = list(result.scalars().all())

        if not reviews:
            return {"provider_id": str(provider_id), "total_reviews": 0, "average_sentiment": "neutral"}

        sentiments = [self.analyze_text(review.comment) for review in reviews]

        avg_compound = sum(s["compound"] for s in sentiments) / len(sentiments)
        positive_count = sum(1 for s in sentiments if s["sentiment"] == "positive")
        negative_count = sum(1 for s in sentiments if s["sentiment"] == "negative")

        return {
            "provider_id": str(provider_id),
            "total_reviews": len(reviews),
            "average_compound": round(avg_compound, 3),
            "positive_reviews": positive_count,
            "negative_reviews": negative_count,
            "positive_percentage": round((positive_count / len(reviews)) * 100, 1),
            "overall_sentiment": "positive" if avg_compound >= 0.05 else "negative" if avg_compound <= -0.05 else "neutral",
        }
