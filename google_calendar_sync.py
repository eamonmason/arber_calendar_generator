"""Google Calendar synchronization module."""

import hashlib
import time
from datetime import datetime
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import config

# Google Calendar API scopes
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Event ID prefix for Arbor-sourced events
ARBOR_EVENT_PREFIX = "arbor_"


class GoogleCalendarSync:
    """Handles synchronization with Google Calendar."""

    def __init__(self, calendar_id: str = "primary") -> None:
        """
        Initialize Google Calendar sync.

        Args:
            calendar_id: Google Calendar ID to sync with
        """
        self.calendar_id = calendar_id
        self.service = None
        self._credentials = None

    def authenticate(self) -> bool:
        """
        Authenticate with Google Calendar API.

        Returns:
            True if authentication successful, False otherwise
        """
        creds = None
        token_path = config.token_path
        credentials_path = config.credentials_path

        # Load existing token
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"Failed to refresh credentials: {e}")
                    creds = None

            if not creds:
                if not credentials_path.exists():
                    print(f"Credentials file not found at {credentials_path}")
                    print("Please run the setup script first or set up OAuth2 credentials manually.")
                    return False

                try:
                    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    print(f"Failed to authenticate: {e}")
                    return False

            # Save the credentials for the next run
            try:
                token_path.parent.mkdir(parents=True, exist_ok=True)
                with open(token_path, "w") as token:
                    token.write(creds.to_json())
            except Exception as e:
                print(f"Warning: Could not save token: {e}")

        self._credentials = creds

        try:
            self.service = build("calendar", "v3", credentials=creds)
            # Test the connection
            self.service.calendars().get(calendarId=self.calendar_id).execute()
            print("Successfully authenticated with Google Calendar")
            return True
        except HttpError as e:
            print(f"Failed to connect to Google Calendar: {e}")
            return False
        except Exception as e:
            print(f"Authentication error: {e}")
            return False

    def generate_event_id(self, lesson: dict[str, Any]) -> str:
        """
        Generate a stable, unique event ID for an Arbor lesson.

        Args:
            lesson: Lesson dictionary with keys: subject, staff, from_date, to_date, class_location

        Returns:
            Unique event ID for the lesson
        """
        # Create a hash from lesson details that won't change
        hash_input = f"{lesson['subject']}|{lesson['from_date']}|{lesson['staff']}"
        if lesson.get('class_location'):
            hash_input += f"|{lesson['class_location']}"

        # Create hash and encode for Google Calendar ID requirements
        hash_obj = hashlib.sha256(hash_input.encode('utf-8'))
        hash_hex = hash_obj.hexdigest()[:20]  # Limit length

        return f"{ARBOR_EVENT_PREFIX}{hash_hex}"

    def lesson_to_event(self, lesson: dict[str, Any], include_id: bool = True) -> dict[str, Any]:
        """
        Convert an Arbor lesson to Google Calendar event format.

        Args:
            lesson: Lesson dictionary from Arbor
            include_id: Whether to include the custom ID (False for creation)

        Returns:
            Google Calendar event dictionary
        """
        # Convert datetime objects to RFC3339 format
        start_time = lesson["from_date"].isoformat()
        end_time = lesson["to_date"].isoformat()

        event = {
            "summary": lesson["subject"],
            "description": f"Staff: {lesson['staff']}\nSource: Arbor Calendar Sync\nID: {self.generate_event_id(lesson)}",
            "start": {
                "dateTime": start_time,
                "timeZone": config.arbor_timezone,
            },
            "end": {
                "dateTime": end_time,
                "timeZone": config.arbor_timezone,
            },
            "source": {
                "title": "Arbor Calendar Sync",
                "url": config.arbor_base_url,
            },
        }

        if include_id:
            event["id"] = self.generate_event_id(lesson)

        if lesson.get("class_location"):
            event["location"] = lesson["class_location"]

        return event

    def fetch_existing_events(self, start_date: datetime, end_date: datetime) -> list[dict[str, Any]]:
        """
        Fetch existing Arbor events from Google Calendar.

        Args:
            start_date: Start date for event search
            end_date: End date for event search

        Returns:
            List of existing Arbor events
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        try:
            # Convert to RFC3339 format
            time_min = start_date.isoformat() + "Z"
            time_max = end_date.isoformat() + "Z"

            events_result = (
                self.service.events()
                .list(
                    calendarId=self.calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=2500,  # High limit to get all events
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            all_events = events_result.get("items", [])
            # Filter for events created by Arbor Calendar Sync (look in description)
            events = []
            for event in all_events:
                description = event.get("description", "")
                if "Source: Arbor Calendar Sync" in description and "ID: arbor_" in description:
                    events.append(event)

            print(f"Found {len(events)} existing Arbor events in Google Calendar")
            return events

        except HttpError as e:
            print(f"Failed to fetch existing events: {e}")
            return []

    def reconcile_events(
        self, arbor_lessons: list[dict[str, Any]], existing_events: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        """
        Reconcile Arbor lessons with existing Google Calendar events.

        Args:
            arbor_lessons: List of lessons from Arbor
            existing_events: List of existing events from Google Calendar

        Returns:
            Tuple of (events_to_create, events_to_update, event_ids_to_delete)
        """
        # Convert Arbor lessons to events
        arbor_events = [self.lesson_to_event(lesson) for lesson in arbor_lessons]
        arbor_event_ids = {self.generate_event_id(lesson) for lesson in arbor_lessons}

        # Extract Arbor IDs from existing event descriptions and map them
        def extract_arbor_id(description: str) -> str | None:
            if "ID: arbor_" in description:
                start = description.find("ID: arbor_") + 4
                end = description.find("\n", start)
                if end == -1:
                    end = len(description)
                return description[start:end].strip()
            return None

        existing_event_map = {}
        for event in existing_events:
            arbor_id = extract_arbor_id(event.get("description", ""))
            if arbor_id:
                existing_event_map[arbor_id] = event

        existing_arbor_ids = set(existing_event_map.keys())

        # Determine what needs to be done
        events_to_create = []
        events_to_update = []
        event_ids_to_delete = []

        # Find events to create or update
        for lesson in arbor_lessons:
            arbor_id = self.generate_event_id(lesson)

            if arbor_id not in existing_arbor_ids:
                # New event - create without custom ID
                event = self.lesson_to_event(lesson, include_id=False)
                events_to_create.append(event)
            elif config.update_existing_events:
                # Check if event needs updating
                existing_event = existing_event_map[arbor_id]
                new_event_data = self.lesson_to_event(lesson, include_id=False)
                if self._event_needs_update(new_event_data, existing_event):
                    # For updates, we need the Google Calendar event ID
                    new_event_data["id"] = existing_event["id"]
                    events_to_update.append(new_event_data)

        # Find events to delete (only if configured to do so)
        if config.delete_orphaned_events:
            orphaned_arbor_ids = existing_arbor_ids - arbor_event_ids
            event_ids_to_delete = [existing_event_map[arbor_id]["id"] for arbor_id in orphaned_arbor_ids]

        return events_to_create, events_to_update, event_ids_to_delete

    def _event_needs_update(self, arbor_event: dict[str, Any], existing_event: dict[str, Any]) -> bool:
        """
        Check if an existing event needs to be updated.

        Args:
            arbor_event: Event data from Arbor
            existing_event: Existing event from Google Calendar

        Returns:
            True if event needs updating, False otherwise
        """
        # Check key fields that might change
        fields_to_check = ["summary", "description", "location", "start", "end"]

        for field in fields_to_check:
            arbor_value = arbor_event.get(field)
            existing_value = existing_event.get(field)

            # Handle None vs empty string differences
            if (arbor_value or existing_value) and arbor_value != existing_value:
                return True

        return False

    def sync_events(
        self, arbor_lessons: list[dict[str, Any]], dry_run: bool = False
    ) -> dict[str, int]:
        """
        Sync Arbor lessons to Google Calendar.

        Args:
            arbor_lessons: List of lessons from Arbor
            dry_run: If True, only show what would be changed without making changes

        Returns:
            Dictionary with counts of created, updated, and deleted events
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        print("Fetching existing events...")
        # Use date range from lessons
        if not arbor_lessons:
            return {"created": 0, "updated": 0, "deleted": 0}

        start_dates = [lesson["from_date"] for lesson in arbor_lessons]
        end_dates = [lesson["to_date"] for lesson in arbor_lessons]
        range_start = min(start_dates)
        range_end = max(end_dates)

        existing_events = self.fetch_existing_events(range_start, range_end)

        print("Reconciling events...")
        events_to_create, events_to_update, event_ids_to_delete = self.reconcile_events(
            arbor_lessons, existing_events
        )

        stats = {
            "created": len(events_to_create),
            "updated": len(events_to_update),
            "deleted": len(event_ids_to_delete),
        }

        print(f"Plan: Create {stats['created']}, Update {stats['updated']}, Delete {stats['deleted']} events")

        if dry_run:
            print("Dry run mode - no changes made")
            return stats

        # Execute changes
        try:
            # Create new events with rate limiting
            for i, event in enumerate(events_to_create):
                if i > 0 and i % 10 == 0:
                    print(f"  Created {i}/{len(events_to_create)} events, pausing...")
                    time.sleep(1)  # Pause after every 10 events

                # Create event without custom ID (Google will generate one)
                self.service.events().insert(calendarId=self.calendar_id, body=event).execute()
                time.sleep(0.1)  # Small delay between each event

            # Update existing events with rate limiting
            for i, event in enumerate(events_to_update):
                if i > 0 and i % 10 == 0:
                    print(f"  Updated {i}/{len(events_to_update)} events, pausing...")
                    time.sleep(1)

                self.service.events().update(
                    calendarId=self.calendar_id, eventId=event["id"], body=event
                ).execute()
                time.sleep(0.1)

            # Delete orphaned events with rate limiting
            for i, event_id in enumerate(event_ids_to_delete):
                if i > 0 and i % 10 == 0:
                    print(f"  Deleted {i}/{len(event_ids_to_delete)} events, pausing...")
                    time.sleep(1)

                self.service.events().delete(
                    calendarId=self.calendar_id, eventId=event_id
                ).execute()
                time.sleep(0.1)

            print(f"Successfully synced events: Created {stats['created']}, Updated {stats['updated']}, Deleted {stats['deleted']}")

        except HttpError as e:
            print(f"Error during sync: {e}")
            raise

        return stats
