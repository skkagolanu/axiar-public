"""Unit tests for AI scheduling service."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from app.services.ai_scheduling import AISchedulingService


@pytest.fixture
def ai_service(db_session):
    return AISchedulingService(db_session)


@pytest.mark.asyncio
async def test_get_scheduling_suggestions_success(ai_service):
    """Test successful scheduling suggestions."""
    mock_jobs = [
        {"id": 1, "title": "Plumbing repair", "priority": "high", "duration": 120},
        {"id": 2, "title": "HVAC maintenance", "priority": "medium", "duration": 90},
    ]
    mock_providers = [
        {"id": 1, "name": "John Doe", "skills": ["plumbing"], "availability": True},
        {"id": 2, "name": "Jane Smith", "skills": ["hvac"], "availability": True},
    ]

    with patch.object(ai_service.ai_assistant, "generate_response") as mock_generate:
        mock_generate.return_value = "Assign job 1 to provider 1 at 9:00 AM, job 2 to provider 2 at 11:00 AM"

        result = await ai_service.get_scheduling_suggestions(
            date=datetime.now().date(), jobs=mock_jobs, providers=mock_providers
        )

        assert "suggestions" in result
        assert len(result["suggestions"]) > 0
        mock_generate.assert_called_once()


@pytest.mark.asyncio
async def test_auto_assign_jobs_success(ai_service):
    """Test auto-assign jobs."""
    mock_jobs = [{"id": 1, "title": "Emergency repair", "priority": "high"}]
    mock_providers = [{"id": 1, "name": "John Doe", "availability": True}]

    with patch.object(ai_service.ai_assistant, "generate_response") as mock_generate:
        mock_generate.return_value = "Assign job 1 to provider 1"

        result = await ai_service.auto_assign_jobs(jobs=mock_jobs, providers=mock_providers)

        assert "assignments" in result
        assert result["success"] is True


@pytest.mark.asyncio
async def test_get_scheduling_suggestions_no_ai(ai_service):
    """Test fallback when AI unavailable."""
    ai_service.ai_assistant = None

    result = await ai_service.get_scheduling_suggestions(date=datetime.now().date(), jobs=[], providers=[])

    assert "suggestions" in result
    assert result["suggestions"][0]["message"] == "AI assistant not available"
