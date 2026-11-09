from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from uuid import UUID

from app.domain.booking.models import Booking
from app.domain.booking_rules.rules import BookingRule


class RuleEngine:
    """Evaluate booking rules for auto-acceptance"""

    @staticmethod
    def evaluate_rule(rule: BookingRule, booking_data: Dict[str, Any], existing_bookings: list[Booking]) -> bool:
        """Evaluate if booking meets rule conditions"""
        conditions = rule.conditions
        scheduled_time = booking_data.get("scheduled_time")

        if not scheduled_time:
            return False

        # Check minimum advance hours
        if "min_advance_hours" in conditions:
            min_hours = conditions["min_advance_hours"]
            advance_hours = (scheduled_time - datetime.now()).total_seconds() / 3600
            if advance_hours < min_hours:
                return False

        # Check allowed days of week (0=Monday, 6=Sunday)
        if "allowed_days" in conditions:
            allowed_days = conditions["allowed_days"]
            if scheduled_time.weekday() not in allowed_days:
                return False

        # Check max bookings per day
        if "max_bookings_per_day" in conditions:
            max_per_day = conditions["max_bookings_per_day"]
            same_day_bookings = [b for b in existing_bookings if b.scheduled_time.date() == scheduled_time.date()]
            if len(same_day_bookings) >= max_per_day:
                return False

        # Check time range
        if "allowed_hours" in conditions:
            allowed_hours = conditions["allowed_hours"]  # e.g., {"start": 9, "end": 17}
            hour = scheduled_time.hour
            if hour < allowed_hours.get("start", 0) or hour >= allowed_hours.get("end", 24):
                return False

        # Check minimum service value
        if "min_value_cents" in conditions:
            min_value = conditions["min_value_cents"]
            if booking_data.get("base_price_cents", 0) < min_value:
                return False

        return True

    @staticmethod
    def should_auto_accept(
        rules: list[BookingRule], booking_data: Dict[str, Any], existing_bookings: list[Booking]
    ) -> tuple[bool, Optional[str]]:
        """
        Determine if booking should be auto-accepted
        Returns: (should_accept, reason)
        """
        if not rules:
            return False, "No rules configured"

        # Sort by priority (higher first)
        sorted_rules = sorted(rules, key=lambda r: r.priority, reverse=True)

        for rule in sorted_rules:
            if not rule.is_active:
                continue

            if RuleEngine.evaluate_rule(rule, booking_data, existing_bookings):
                return True, f"Auto-accepted by rule: {rule.name}"

        return False, "No matching rules"
