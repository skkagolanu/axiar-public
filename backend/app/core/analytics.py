import statistics
from datetime import datetime, timedelta
from typing import Any, Dict, List
from uuid import UUID


class PredictiveAnalytics:
    """Predictive analytics for business insights"""

    @staticmethod
    def forecast_demand(historical_bookings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Forecast booking demand for next 7 days"""
        if not historical_bookings:
            return {"forecast": [0] * 7, "confidence": 0}

        # Group by day of week
        day_counts: List[List[int]] = [[] for _ in range(7)]
        for booking in historical_bookings:
            day = booking["scheduled_time"].weekday()
            day_counts[day].append(1)

        # Calculate average per day
        forecast = []
        for day_bookings in day_counts:
            if day_bookings:
                avg = statistics.mean(day_bookings)
                forecast.append(round(avg))
            else:
                forecast.append(0)

        confidence = len(historical_bookings) / 100  # Simple confidence metric
        return {"forecast": forecast, "confidence": min(confidence, 1.0)}

    @staticmethod
    def predict_no_show(booking_data: Dict[str, Any]) -> Dict[str, Any]:
        """Predict likelihood of booking no-show"""
        score = 0.0

        # Advance booking time (less advance = higher risk)
        advance_hours = (booking_data["scheduled_time"] - datetime.now()).total_seconds() / 3600
        if advance_hours < 24:
            score += 0.3
        elif advance_hours < 48:
            score += 0.1

        # First-time customer (higher risk)
        if booking_data.get("is_first_booking", False):
            score += 0.2

        # Low booking value (higher risk)
        if booking_data.get("base_price_cents", 0) < 5000:  # < £50
            score += 0.15

        # Weekend booking (slightly higher risk)
        if booking_data["scheduled_time"].weekday() >= 5:
            score += 0.1

        risk_level = "high" if score > 0.5 else "medium" if score > 0.3 else "low"

        return {"probability": min(score, 1.0), "risk_level": risk_level, "factors": []}

    @staticmethod
    def suggest_dynamic_pricing(booking_data: Dict[str, Any], demand_forecast: Dict[str, Any]) -> Dict[str, Any]:
        """Suggest dynamic pricing based on demand"""
        base_price = booking_data.get("base_price_cents", 0)
        day = booking_data["scheduled_time"].weekday()

        # Get demand for that day
        forecast = demand_forecast.get("forecast", [0] * 7)
        day_demand = forecast[day] if day < len(forecast) else 0
        avg_demand = statistics.mean(forecast) if forecast else 0

        # Calculate multiplier
        if avg_demand == 0:
            multiplier = 1.0
        else:
            demand_ratio = day_demand / avg_demand
            if demand_ratio > 1.5:
                multiplier = 1.2  # 20% increase
            elif demand_ratio > 1.2:
                multiplier = 1.1  # 10% increase
            elif demand_ratio < 0.7:
                multiplier = 0.9  # 10% discount
            else:
                multiplier = 1.0

        suggested_price = int(base_price * multiplier)

        return {
            "base_price_cents": base_price,
            "suggested_price_cents": suggested_price,
            "multiplier": multiplier,
            "reason": f"Demand ratio: {demand_ratio:.2f}" if avg_demand > 0 else "Insufficient data",
        }

    @staticmethod
    def optimize_resource_allocation(bookings: List[Dict[str, Any]], agents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Optimize field agent allocation"""
        if not bookings or not agents:
            return {"recommendations": []}

        # Group bookings by time slot
        time_slots: Dict[int, List[Dict[str, Any]]] = {}
        for booking in bookings:
            hour = booking["scheduled_time"].hour
            if hour not in time_slots:
                time_slots[hour] = []
            time_slots[hour].append(booking)

        # Find peak hours
        peak_hours = sorted(time_slots.items(), key=lambda x: len(x[1]), reverse=True)[:3]

        recommendations = []
        for hour, slot_bookings in peak_hours:
            required_agents = len(slot_bookings)
            recommendations.append(
                {
                    "time_slot": f"{hour:02d}:00-{hour+1:02d}:00",
                    "bookings_count": len(slot_bookings),
                    "recommended_agents": required_agents,
                }
            )

        return {"recommendations": recommendations, "total_agents_needed": len(agents)}


analytics = PredictiveAnalytics()
