"""Unit tests for Google Calendar sync functionality."""

import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from google_calendar_sync import GoogleCalendarSync


@pytest.fixture
def calendar_sync():
    """Create a Google Calendar sync instance for testing."""
    return GoogleCalendarSync("test_calendar_id")


@pytest.fixture
def sample_lesson():
    """Sample lesson data from Arbor."""
    return {
        "subject": "Mathematics",
        "class_location": "Room 101",
        "staff": "Mr. Smith",
        "from_date": datetime.datetime(2024, 1, 15, 9, 0),
        "to_date": datetime.datetime(2024, 1, 15, 10, 0),
    }


@pytest.fixture
def sample_lessons():
    """Sample list of lessons from Arbor."""
    return [
        {
            "subject": "Mathematics",
            "class_location": "Room 101",
            "staff": "Mr. Smith",
            "from_date": datetime.datetime(2024, 1, 15, 9, 0),
            "to_date": datetime.datetime(2024, 1, 15, 10, 0),
        },
        {
            "subject": "English",
            "class_location": None,
            "staff": "Ms. Johnson",
            "from_date": datetime.datetime(2024, 1, 16, 10, 0),
            "to_date": datetime.datetime(2024, 1, 16, 11, 0),
        },
    ]


@pytest.fixture
def sample_google_event():
    """Sample Google Calendar event."""
    return {
        "id": "arbor_1234567890abcdef",
        "summary": "Mathematics",
        "description": "Staff: Mr. Smith",
        "location": "Room 101",
        "start": {
            "dateTime": "2024-01-15T09:00:00",
            "timeZone": "Europe/London",
        },
        "end": {
            "dateTime": "2024-01-15T10:00:00",
            "timeZone": "Europe/London",
        },
    }


class TestGoogleCalendarSync:
    """Test cases for GoogleCalendarSync class."""

    def test_init(self, calendar_sync):
        """Test initialization."""
        assert calendar_sync.calendar_id == "test_calendar_id"
        assert calendar_sync.service is None

    def test_generate_event_id(self, calendar_sync, sample_lesson):
        """Test event ID generation."""
        event_id = calendar_sync.generate_event_id(sample_lesson)

        # Should start with arbor prefix
        assert event_id.startswith("arbor_")

        # Should be consistent for same lesson
        event_id2 = calendar_sync.generate_event_id(sample_lesson)
        assert event_id == event_id2

        # Should be different for different lessons
        different_lesson = sample_lesson.copy()
        different_lesson["subject"] = "Physics"
        different_id = calendar_sync.generate_event_id(different_lesson)
        assert event_id != different_id

    def test_generate_event_id_no_location(self, calendar_sync):
        """Test event ID generation without location."""
        lesson = {
            "subject": "English",
            "class_location": None,
            "staff": "Ms. Johnson",
            "from_date": datetime.datetime(2024, 1, 16, 10, 0),
            "to_date": datetime.datetime(2024, 1, 16, 11, 0),
        }

        event_id = calendar_sync.generate_event_id(lesson)
        assert event_id.startswith("arbor_")

    def test_lesson_to_event(self, calendar_sync, sample_lesson):
        """Test conversion of lesson to Google Calendar event."""
        event = calendar_sync.lesson_to_event(sample_lesson)

        assert event["id"].startswith("arbor_")
        assert event["summary"] == "Mathematics"
        assert "Staff: Mr. Smith" in event["description"]
        assert "Source: Arbor Calendar Sync" in event["description"]
        assert "ID: arbor_" in event["description"]
        assert event["location"] == "Room 101"
        assert event["start"]["dateTime"] == "2024-01-15T09:00:00"
        assert event["end"]["dateTime"] == "2024-01-15T10:00:00"
        assert event["start"]["timeZone"] == "Europe/London"
        assert event["source"]["title"] == "Arbor Calendar Sync"

    def test_lesson_to_event_no_location(self, calendar_sync):
        """Test conversion of lesson without location."""
        lesson = {
            "subject": "English",
            "class_location": None,
            "staff": "Ms. Johnson",
            "from_date": datetime.datetime(2024, 1, 16, 10, 0),
            "to_date": datetime.datetime(2024, 1, 16, 11, 0),
        }

        event = calendar_sync.lesson_to_event(lesson)

        assert "location" not in event
        assert event["summary"] == "English"
        assert "Staff: Ms. Johnson" in event["description"]
        assert "Source: Arbor Calendar Sync" in event["description"]
        assert "ID: arbor_" in event["description"]

    @patch("google_calendar_sync.build")
    @patch("google_calendar_sync.Credentials")
    def test_authenticate_success(self, mock_creds, mock_build, calendar_sync):
        """Test successful authentication."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Mock successful calendar access test
        mock_service.calendars().get().execute.return_value = {"id": "test_calendar"}

        with patch("google_calendar_sync.config") as mock_config:
            mock_config.token_path.exists.return_value = True
            mock_config.credentials_path.exists.return_value = True

            mock_creds.from_authorized_user_file.return_value.valid = True

            result = calendar_sync.authenticate()

        assert result is True
        assert calendar_sync.service is mock_service

    def test_authenticate_no_service(self, calendar_sync):
        """Test sync_events without authentication."""
        with pytest.raises(RuntimeError, match="Not authenticated"):
            calendar_sync.sync_events([])

    def test_reconcile_events_create_only(self, calendar_sync, sample_lessons):
        """Test reconciling events when all need to be created."""
        existing_events: list[dict[str, Any]] = []

        events_to_create, events_to_update, event_ids_to_delete = (
            calendar_sync.reconcile_events(sample_lessons, existing_events)
        )

        assert len(events_to_create) == 2
        assert len(events_to_update) == 0
        assert len(event_ids_to_delete) == 0

        # Check first event
        assert events_to_create[0]["summary"] == "Mathematics"
        assert events_to_create[1]["summary"] == "English"

    def test_reconcile_events_mixed_operations(self, calendar_sync, sample_lessons):
        """Test reconciling events with mixed create/update/delete operations."""
        # Create existing event that matches first lesson exactly
        math_arbor_id = calendar_sync.generate_event_id(sample_lessons[0])
        existing_events = [
            {
                "id": "google_math_event",
                "summary": "Mathematics",
                "description": f"Staff: Mr. Smith\nSource: Arbor Calendar Sync\nID: {math_arbor_id}",
                "location": "Room 101",
                "start": {
                    "dateTime": "2024-01-15T09:00:00",
                    "timeZone": "Europe/London",
                },
                "end": {"dateTime": "2024-01-15T10:00:00", "timeZone": "Europe/London"},
            },
            {
                "id": "arbor_orphaned_event",
                "summary": "Deleted Subject",
                "description": "Staff: Old Teacher\nSource: Arbor Calendar Sync\nID: arbor_orphaned123",
            },
        ]

        with patch("google_calendar_sync.config") as mock_config:
            mock_config.update_existing_events = True
            mock_config.delete_orphaned_events = True
            mock_config.arbor_timezone = "Europe/London"

            events_to_create, events_to_update, event_ids_to_delete = (
                calendar_sync.reconcile_events(sample_lessons, existing_events)
            )

        # Should create English lesson (new)
        assert len(events_to_create) == 1
        assert events_to_create[0]["summary"] == "English"

        # Should not update math lesson (unchanged)
        assert len(events_to_update) == 0

        # Should delete orphaned event
        assert len(event_ids_to_delete) == 1
        assert event_ids_to_delete[0] == "arbor_orphaned_event"

    def test_reconcile_events_update_needed(self, calendar_sync, sample_lessons):
        """Test reconciling when an event needs updating."""
        # Create existing event with different summary but proper Arbor ID in description
        math_arbor_id = calendar_sync.generate_event_id(sample_lessons[0])
        existing_events = [
            {
                "id": "google_event_id_123",  # Different from Arbor ID
                "summary": "Old Mathematics",  # Different summary
                "description": f"Staff: Mr. Smith\nSource: Arbor Calendar Sync\nID: {math_arbor_id}",
                "location": "Room 101",
                "start": {
                    "dateTime": "2024-01-15T09:00:00",
                    "timeZone": "Europe/London",
                },
                "end": {"dateTime": "2024-01-15T10:00:00", "timeZone": "Europe/London"},
            }
        ]

        with patch("google_calendar_sync.config") as mock_config:
            mock_config.update_existing_events = True
            mock_config.delete_orphaned_events = True
            mock_config.arbor_timezone = "Europe/London"

            events_to_create, events_to_update, event_ids_to_delete = (
                calendar_sync.reconcile_events(sample_lessons[:1], existing_events)
            )

        # Should create nothing, update math, delete nothing
        assert len(events_to_create) == 0
        assert len(events_to_update) == 1
        assert len(event_ids_to_delete) == 0

        # Check updated event
        assert events_to_update[0]["summary"] == "Mathematics"
        assert events_to_update[0]["id"] == "google_event_id_123"

    def test_event_needs_update(self, calendar_sync):
        """Test _event_needs_update method."""
        arbor_event = {
            "summary": "Mathematics",
            "description": "Staff: Mr. Smith",
            "location": "Room 101",
        }

        # Same event - no update needed
        existing_event = arbor_event.copy()
        assert calendar_sync._event_needs_update(arbor_event, existing_event) is False

        # Different summary - update needed
        existing_event = arbor_event.copy()
        existing_event["summary"] = "Old Mathematics"
        assert calendar_sync._event_needs_update(arbor_event, existing_event) is True

        # Different location - update needed
        existing_event = arbor_event.copy()
        existing_event["location"] = "Room 102"
        assert calendar_sync._event_needs_update(arbor_event, existing_event) is True

        # Missing location in existing - update needed
        existing_event = arbor_event.copy()
        del existing_event["location"]
        assert calendar_sync._event_needs_update(arbor_event, existing_event) is True

    @patch("google_calendar_sync.build")
    def test_fetch_existing_events_success(self, mock_build, calendar_sync):
        """Test successful fetching of existing events."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        calendar_sync.service = mock_service

        # Mock API response - include both Arbor and non-Arbor events
        mock_service.events().list().execute.return_value = {
            "items": [
                {
                    "id": "arbor_test123",
                    "summary": "Test Event",
                    "description": "Source: Arbor Calendar Sync\nID: arbor_test123",
                },
                {
                    "id": "other_event",
                    "summary": "Other Event",
                    "description": "Not from Arbor",
                },
            ]
        }

        start_date = datetime.datetime(2024, 1, 1)
        end_date = datetime.datetime(2024, 1, 31)

        events = calendar_sync.fetch_existing_events(start_date, end_date)

        # Should only return the Arbor event, filtering out the other event
        assert len(events) == 1
        assert events[0]["id"] == "arbor_test123"

        # Verify API call parameters - the chain events().list() gets called
        mock_service.events().list.assert_called_once()
        # Get the call arguments from the mock
        call_args = mock_service.events().list.call_args[1]
        assert call_args["calendarId"] == "test_calendar_id"
        assert "timeMin" in call_args
        assert "timeMax" in call_args
        assert call_args["maxResults"] == 2500
        assert call_args["singleEvents"] is True
        assert call_args["orderBy"] == "startTime"

    def test_fetch_existing_events_not_authenticated(self, calendar_sync):
        """Test fetching events without authentication."""
        start_date = datetime.datetime(2024, 1, 1)
        end_date = datetime.datetime(2024, 1, 31)

        with pytest.raises(RuntimeError, match="Not authenticated"):
            calendar_sync.fetch_existing_events(start_date, end_date)

    @patch("google_calendar_sync.build")
    def test_sync_events_dry_run(self, mock_build, calendar_sync, sample_lessons):
        """Test sync events in dry run mode."""
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        calendar_sync.service = mock_service

        # Mock fetch_existing_events to return empty list
        with patch.object(calendar_sync, "fetch_existing_events", return_value=[]):
            stats = calendar_sync.sync_events(sample_lessons, dry_run=True)

        # Should not make any API calls for actual changes
        mock_service.events().insert.assert_not_called()
        mock_service.events().update.assert_not_called()
        mock_service.events().delete.assert_not_called()

        # Should return expected stats
        assert stats["created"] == 2
        assert stats["updated"] == 0
        assert stats["deleted"] == 0

    def test_sync_events_empty_lessons(self, calendar_sync):
        """Test sync events with empty lesson list."""
        # Mock the service to avoid authentication requirement
        calendar_sync.service = MagicMock()

        stats = calendar_sync.sync_events([], dry_run=True)

        assert stats["created"] == 0
        assert stats["updated"] == 0
        assert stats["deleted"] == 0
