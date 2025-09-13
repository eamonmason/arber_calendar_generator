"""
Generate a school calendar from the Arbor API.

This script uses Playwright to interact with the Arbor web interface,
allows interactive login, retrieves calendar entries for a given date range,
and creates an iCalendar file from the lessons.

Usage: python generate_school_calendar.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
"""

import argparse
import asyncio
import datetime
import json

import bs4 as bs
import dateutil.tz
import icalendar
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from config import config


def get_academic_year_dates(year: int | None = None) -> tuple[datetime.date, datetime.date]:
    """
    Get the start and end dates for the UK academic year.

    UK academic year runs from September 1st to July 31st of the following year.

    Args:
        year: The calendar year for September (start of academic year).
               If None, automatically determines based on current date.

    Returns:
        Tuple of (start_date, end_date) for the academic year.
    """
    if year is None:
        current_date = datetime.date.today()
        # If we're in January-August, use previous year's September
        # If we're in September-December, use current year's September
        year = current_date.year if current_date.month >= 9 else current_date.year - 1

    start_date = datetime.date(year, 9, 1)
    end_date = datetime.date(year + 1, 7, 31)

    return start_date, end_date


class ArborCalendarGenerator:
    """Main class for generating school calendars from Arbor API."""

    def __init__(self) -> None:
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start_browser(self, headless: bool = True) -> None:
        """Start the Playwright browser with error handling."""
        import os

        # Clean up any existing browser resources first
        if hasattr(self, 'context') and self.context and not self.context._closed:
            try:
                await self.context.close()
            except:
                pass
        if hasattr(self, 'browser') and self.browser:
            try:
                await self.browser.close()
            except:
                pass

        playwright = await async_playwright().start()

        # Add Lambda-specific browser arguments
        launch_args = []
        if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
            launch_args = [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--no-zygote',
                '--single-process',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--disable-extensions',
                '--disable-default-apps',
                '--disable-background-networking',
                '--disable-sync'
            ]

        self.browser = await playwright.chromium.launch(
            headless=headless,
            args=launch_args
        )

        self.context = await self.browser.new_context(
            ignore_https_errors=True,  # Ignore SSL certificate errors
            extra_http_headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        )
        self.page = await self.context.new_page()

    async def close_browser(self) -> None:
        """Close the browser and cleanup resources safely."""
        try:
            if hasattr(self, 'page') and self.page and not self.page.is_closed():
                await self.page.close()
        except Exception as e:
            print(f"Warning: Error closing page: {e}")

        try:
            if hasattr(self, 'context') and self.context and not self.context._closed:
                await self.context.close()
        except Exception as e:
            print(f"Warning: Error closing context: {e}")

        try:
            if hasattr(self, 'browser') and self.browser:
                await self.browser.close()
        except Exception as e:
            print(f"Warning: Error closing browser: {e}")

        # Reset references
        self.page = None
        self.context = None
        self.browser = None

    async def interactive_login(self) -> None:
        """Perform interactive login to Arbor."""
        if not self.page:
            raise RuntimeError("Browser not started. Call start_browser() first.")

        # Try base URL first since /auth/login might be broken
        await self.page.goto(config.arbor_base_url)
        print("Navigating to Arbor base URL...")

        # Check if we have credentials for automatic login
        username = config.arbor_username
        password = config.arbor_password

        if username and password:
            print("Attempting automatic login with provided credentials...")
            try:
                await self._automatic_login(username, password)
                print("Automatic login completed!")
            except Exception as e:
                print(f"Automatic login failed: {e}")
                print("Falling back to manual login...")
                await self._manual_login()
        else:
            print("No credentials provided, using manual login...")
            await self._manual_login()

        # Verify we're logged in by checking for common elements
        try:
            await self.page.wait_for_selector(".header, .navigation, .main-content", timeout=10000)
            print("Login successful!")
        except Exception:
            print("Warning: Could not verify login status. Continuing anyway...")

    async def _automatic_login(self, username: str, password: str) -> None:
        """Attempt automatic login with provided credentials."""
        # Wait for page to load
        await asyncio.sleep(2)

        # Look for common login form elements
        login_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[name="username"]',
            'input[name="user"]',
            'input[id="email"]',
            'input[id="username"]'
        ]

        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[id="password"]'
        ]

        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Log in")',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            '.login-button',
            '.btn-login'
        ]

        # Find and fill username field
        username_field = None
        for selector in login_selectors:
            try:
                username_field = await self.page.wait_for_selector(selector, timeout=3000)
                if username_field:
                    break
            except:
                continue

        if not username_field:
            raise RuntimeError("Could not find username field")

        # Find password field
        password_field = None
        for selector in password_selectors:
            try:
                password_field = await self.page.wait_for_selector(selector, timeout=1000)
                if password_field:
                    break
            except:
                continue

        if not password_field:
            raise RuntimeError("Could not find password field")

        # Fill in credentials
        await username_field.fill(username)
        await password_field.fill(password)

        # Find and click submit button
        submit_button = None
        for selector in submit_selectors:
            try:
                submit_button = await self.page.wait_for_selector(selector, timeout=1000)
                if submit_button:
                    break
            except:
                continue

        if not submit_button:
            raise RuntimeError("Could not find submit button")

        # Submit the form
        await submit_button.click()

        # Wait for navigation after login
        try:
            await self.page.wait_for_load_state('networkidle', timeout=10000)
        except:
            # If networkidle fails, wait a bit and continue
            await asyncio.sleep(3)

    async def _manual_login(self) -> None:
        """Perform manual login process."""
        print("Please log in to Arbor in the browser window...")
        print("Press Enter once you have successfully logged in and are on the main page.")

        # Wait for user to complete login
        import sys
        if sys.stdin.isatty():
            try:
                input("Press Enter to continue after logging in...")
            except (EOFError, KeyboardInterrupt):
                print("Login cancelled or failed.")
                raise
        else:
            print("Running in non-interactive mode, assuming login is completed...")
            # Add a small delay to allow any auto-login to complete
            await asyncio.sleep(2)

    async def get_calendar_entries(
        self, start_date: datetime.date, end_date: datetime.date
    ) -> dict:
        """Get the calendar entries for the given date range."""
        if not self.page or self.page.is_closed():
            raise RuntimeError("Browser page is not available or has been closed.")

        if not self.context or self.context._closed:
            raise RuntimeError("Browser context is not available or has been closed.")

        # First navigate to the calendar page to establish session context
        calendar_page_url = f"{config.arbor_base_url}/calendar-entry/list/"
        print(f"Navigating to calendar page: {calendar_page_url}")
        await self.page.goto(calendar_page_url)

        # Wait a moment for the page to load
        await asyncio.sleep(1)

        # Get the student object ID
        student_object_id = config.get("arbor.student_object_id", "7192")

        # Collect all calendar entries for the date range
        all_entries = []
        current_date = start_date

        print(f"Fetching calendar entries from {start_date} to {end_date}")

        while current_date <= end_date:
            # Check if page is still valid before making request
            if not self.page or self.page.is_closed():
                print("Warning: Page was closed during calendar fetching, stopping...")
                break

            # Use the correct URL format: /date/YYYY-MM-DD (not query parameters)
            calendar_api_url = f"{config.arbor_base_url}/guardians/widget-data/get-calendar-data/student-id/{student_object_id}/date/{current_date}"

            try:
                response = await self.page.request.get(calendar_api_url, timeout=30000)  # 30 second timeout

                if response.ok:
                    day_data = await response.json()
                    items = day_data.get('items', [])

                    if items:
                        print(f"  {current_date}: Found {len(items)} entries")
                        all_entries.extend(items)
                    else:
                        print(f"  {current_date}: No entries")
                else:
                    print(f"  {current_date}: HTTP Error {response.status}")

            except Exception as e:
                print(f"  {current_date}: Error - {e}")

            # Move to next day
            current_date += datetime.timedelta(days=1)

            # Small delay to avoid overwhelming the API
            await asyncio.sleep(0.1)

        print(f"Total entries found: {len(all_entries)}")

        # Return in the format expected by the rest of the code
        return {
            "items": all_entries,
            "success": True,
            "total": len(all_entries)
        }

    async def parse_calendar_entries_with_details(self, entries: dict) -> list[dict]:
        """
        Parse calendar entries and fetch detailed information including teacher data.
        For performance, we'll fetch detailed info for a sample of lessons first to test.
        """
        lessons = []

        if "items" not in entries or not isinstance(entries["items"], list):
            return lessons

        total_entries = len(entries["items"])
        print(f"Fetching detailed information for a sample of {min(50, total_entries)} lessons to test teacher extraction...")

        # Process only first 50 lessons as a test
        sample_size = min(50, total_entries)

        for i, item in enumerate(entries["items"][:sample_size]):
            if not isinstance(item, dict) or "fields" not in item:
                continue

            try:
                # First extract basic info from the calendar entry
                basic_lesson = self.extract_basic_lesson_from_fields(item["fields"])

                # Get the URL for detailed lesson information
                url = basic_lesson.get("detail_url")
                if url:
                    # Fetch detailed lesson information
                    detailed_lesson = await self.get_detailed_lesson_info(url)
                    # Merge basic and detailed info
                    lesson = {**basic_lesson, **detailed_lesson}
                else:
                    lesson = basic_lesson

                lessons.append(lesson)

                # Progress indicator every 10 lessons
                if (i + 1) % 10 == 0:
                    print(f"  Processed {i + 1}/{sample_size} detailed lessons...")

                # Small delay to avoid overwhelming the server
                await asyncio.sleep(0.2)

            except Exception as e:
                print(f"Warning: Failed to parse calendar entry {i + 1}: {e}")
                continue

        # For remaining lessons, just use basic extraction without detailed fetching
        if total_entries > sample_size:
            print(f"Processing remaining {total_entries - sample_size} lessons with basic extraction...")
            for item in entries["items"][sample_size:]:
                if not isinstance(item, dict) or "fields" not in item:
                    continue

                try:
                    # Only extract basic info for remaining lessons
                    basic_lesson = self.extract_basic_lesson_from_fields(item["fields"])
                    lessons.append(basic_lesson)
                except Exception as e:
                    print(f"Warning: Failed to parse basic calendar entry: {e}")
                    continue

        return lessons

    def extract_basic_lesson_from_fields(self, fields: dict) -> dict:
        """Extract basic lesson details from calendar entry fields."""
        # Extract the data from fields.{field_name}.value structure
        def get_field_value(field_name: str, default=None):
            field_data = fields.get(field_name, {})
            return field_data.get('value', default)

        # Debug: Print available fields on first few calls to understand structure
        if hasattr(self, '_debug_field_count'):
            self._debug_field_count += 1
        else:
            self._debug_field_count = 1

        if self._debug_field_count <= 3:
            print(f"Debug - Available fields: {list(fields.keys())}")
            for field_name, field_data in fields.items():
                if isinstance(field_data, dict) and 'value' in field_data:
                    print(f"  {field_name}: {field_data['value']}")

        # Get the lesson title and extract subject
        title = get_field_value('title', '')
        # Title format is like: "Maths (KStg3): Year 9: 9X/Ma1"
        if ':' in title:
            subject = title.split(':')[0].strip()
            # Remove grade info in parentheses like "(KStg3)"
            if '(' in subject and ')' in subject:
                subject = subject.split('(')[0].strip()
        else:
            subject = title

        # Get location
        location = get_field_value('location')

        # Get date/time information
        start_datetime_str = get_field_value('start_datetime')
        end_datetime_str = get_field_value('end_datetime')

        if not start_datetime_str or not end_datetime_str:
            raise ValueError("Missing start or end datetime")

        # Parse datetime strings (format: "2025-09-16 08:30:00")
        try:
            from_date = datetime.datetime.strptime(start_datetime_str, "%Y-%m-%d %H:%M:%S")
            to_date = datetime.datetime.strptime(end_datetime_str, "%Y-%m-%d %H:%M:%S")
        except ValueError as e:
            raise ValueError(f"Could not parse datetime: {e}")

        # Get the detail URL for fetching teacher information
        detail_url = get_field_value('url')

        return {
            "subject": subject,
            "class_location": location,
            "from_date": from_date,
            "to_date": to_date,
            "detail_url": detail_url,
            "staff": "Teacher TBD"  # Will be overridden by detailed fetch
        }

    async def get_detailed_lesson_info(self, detail_url: str) -> dict:
        """Fetch detailed lesson information including teacher from the lesson URL."""
        if not self.page or self.page.is_closed():
            print("Warning: Page is closed, cannot fetch detailed lesson info")
            return {"staff": "Teacher TBD"}

        if not self.context or self.context._closed:
            print("Warning: Browser context is closed, cannot fetch detailed lesson info")
            return {"staff": "Teacher TBD"}

        try:
            # Construct the full URL
            full_url = f"{config.arbor_base_url}{detail_url}"

            # Fetch the detailed lesson HTML
            response = await self.page.request.get(full_url)

            if not response.ok:
                print(f"Warning: Failed to fetch lesson details from {full_url}: {response.status}")
                return {"staff": "Teacher TBD"}

            html_content = await response.text()

            # Debug: Log HTML structure for first few requests to understand the format
            if hasattr(self, '_debug_html_count'):
                self._debug_html_count += 1
            else:
                self._debug_html_count = 1

            if self._debug_html_count <= 2:
                print(f"Debug HTML structure for URL {detail_url}:")
                print(f"HTML length: {len(html_content)} chars")
                print(f"HTML preview (first 500 chars): {html_content[:500]}")

            # Extract teacher information from HTML
            lesson_details = self.extract_lesson_details_new(html_content)

            return {
                "staff": lesson_details.get("staff", "Teacher TBD")
            }

        except Exception as e:
            print(f"Warning: Error fetching lesson details from {detail_url}: {e}")
            return {"staff": "Teacher TBD"}

    async def get_calendar_entry(self, tooltip_url: str) -> str:
        """Get the calendar entry details for the given tooltip URL."""
        if not self.page:
            raise RuntimeError("Browser not started. Call start_browser() first.")

        response = await self.page.request.get(f"{config.arbor_base_url}{tooltip_url}")

        if not response.ok:
            raise RuntimeError(f"Failed to fetch calendar entry: {response.status}")

        return await response.text()

    def extract_lesson_details_new(self, content: str) -> dict:
        """Extract lesson details from the JSON response format."""
        import json

        # Initialize result with defaults
        result = {
            "subject": "Unknown Subject",
            "class_location": None,
            "staff": "Teacher TBD",
            "from_date": None,
            "to_date": None
        }

        try:
            # Parse the JSON response
            data = json.loads(content)

            # Navigate the JSON structure to find lesson information
            # Based on the debug output: {"type":"slideover","content":[{"componentName":"Arbor.window.Slideover"...}]}
            if "content" in data and isinstance(data["content"], list):
                for top_level_item in data["content"]:
                    if isinstance(top_level_item, dict) and "content" in top_level_item:
                        for item in top_level_item["content"]:
                            if isinstance(item, dict) and "content" in item:
                                # Look through property rows for lesson details
                                for prop_item in item["content"]:
                                    if isinstance(prop_item, dict) and "props" in prop_item:
                                        props = prop_item["props"]
                                        field_label = props.get("fieldLabel", "").lower()
                                        value = props.get("value", "")

                                        # Debug: Print found properties
                                        if hasattr(self, '_debug_json_count'):
                                            self._debug_json_count += 1
                                        else:
                                            self._debug_json_count = 1

                                        if self._debug_json_count <= 10:  # Show more properties to understand structure
                                            print(f"Found property: '{field_label}' = '{value}'")

                                        # Look for staff/teacher information
                                        if field_label in ['teacher', 'staff', 'tutor', 'instructor', 'taught by']:
                                            if value and value.strip():
                                                result["staff"] = value.strip()
                                                print(f"Found staff in '{field_label}': {result['staff']}")

                                        # Look for other common staff field names
                                        elif 'teacher' in field_label or 'staff' in field_label or 'tutor' in field_label:
                                            if value and value.strip():
                                                result["staff"] = value.strip()
                                                print(f"Found staff in '{field_label}': {result['staff']}")

            # If still no staff found, try searching the entire JSON content as text
            if result["staff"] == "Teacher TBD":
                content_text = json.dumps(data).lower()

                # Look for teacher-related keywords in the JSON
                staff_keywords = ['teacher', 'staff', 'tutor', 'instructor']

                for keyword in staff_keywords:
                    if keyword in content_text:
                        # Try to find patterns like "teacher":"John Smith" or similar
                        import re
                        patterns = [
                            rf'"{keyword}"\s*:\s*"([^"]+)"',
                            rf'"{keyword}"\s*:\s*"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)"',
                            rf'"[^"]*{keyword}[^"]*"\s*:\s*"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)"',
                        ]

                        for pattern in patterns:
                            match = re.search(pattern, content_text, re.IGNORECASE)
                            if match:
                                staff_name = match.group(1).strip()
                                if len(staff_name) > 2:  # Avoid single letters
                                    result["staff"] = staff_name
                                    print(f"Found staff via JSON search with '{keyword}': {result['staff']}")
                                    break

                        if result["staff"] != "Teacher TBD":
                            break

        except json.JSONDecodeError as e:
            print(f"Failed to parse lesson detail JSON: {e}")
            # Fallback to treating it as HTML
            try:
                parser = bs.BeautifulSoup(content, "html.parser")
                # This shouldn't happen based on what we've seen, but just in case
                # Could add HTML parsing fallback here if needed
            except Exception as fallback_e:
                print(f"Fallback HTML parsing also failed: {fallback_e}")

        except Exception as e:
            print(f"Error parsing lesson details: {e}")

        return result

    def extract_lesson_details(self, html: str) -> dict:
        """Extract the lesson details from the HTML."""
        parser = bs.BeautifulSoup(html, "html.parser")

        title_element = parser.select_one(".header > .title")
        if not title_element:
            raise ValueError("Could not find lesson title in HTML")

        subject = title_element.text.split(": Year")[0]
        lesson_details = parser.select(".content > ul > li")

        if len(lesson_details) < 2:
            raise ValueError("Insufficient lesson details in HTML")

        if len(lesson_details) < 3:
            class_location = None
            staff_element = lesson_details[1].select_one("span")
        else:
            location_element = lesson_details[1].select_one("span")
            class_location = (
                location_element.text.split(":")[1].strip()
                if location_element and ":" in location_element.text
                else None
            )
            staff_element = lesson_details[2].select_one("span")

        if not staff_element:
            raise ValueError("Could not find staff information in HTML")

        staff = staff_element.text

        date_element = lesson_details[0].select_one("span")
        if not date_element:
            raise ValueError("Could not find date information in HTML")

        source_date = date_element.text.replace("\n", "")
        parsed_date = " ".join(source_date.split())

        try:
            date_str, time_str = parsed_date.split(", ")[1:]
            from_time, to_time = time_str.split(" - ")
            from_date = datetime.datetime.strptime(f"{date_str} {from_time}", "%d %b %Y %H:%M")
            to_date = datetime.datetime.strptime(f"{date_str} {to_time}", "%d %b %Y %H:%M")
        except (ValueError, IndexError) as e:
            raise ValueError(f"Could not parse date/time information: {e}") from e

        return {
            "subject": subject,
            "class_location": class_location,
            "staff": staff,
            "from_date": from_date,
            "to_date": to_date,
        }

    def create_calendar_event(self, lesson: dict) -> icalendar.Event:
        """Create an iCalendar event from the lesson details."""
        e = icalendar.Event()
        tz = dateutil.tz.tzstr(config.arbor_timezone)
        e.add("summary", lesson["subject"])
        e.add("location", lesson["class_location"])

        # Only add teacher information if it's actually available (not a placeholder)
        staff = lesson.get("staff", "")
        if staff and staff != "Teacher TBD" and not staff.startswith("Teacher ("):
            e.add("description", staff)

        e.add("dtstart", lesson["from_date"].astimezone(tz))
        e.add("dtend", lesson["to_date"].astimezone(tz))
        return e

    def create_calendar(self, lesson_list: list[dict]) -> icalendar.Calendar:
        """Create an iCalendar from the list of lessons."""
        cal = icalendar.Calendar()
        cal.add("prodid", config.get("calendar.prod_id", "-//Tiffin School//Tiffin School Calendar//EN"))
        cal.add("version", "2.0")
        for lesson in lesson_list:
            cal.add_component(self.create_calendar_event(lesson))
        return cal


    async def fetch_lessons(
        self, start_date: datetime.date, end_date: datetime.date, headless: bool = True
    ) -> list[dict]:
        """
        Fetch all lessons from Arbor for the given date range.

        Returns:
            List of lesson dictionaries with keys: subject, class_location, staff, from_date, to_date
        """
        try:
            await self.start_browser(headless=headless)
            await self.interactive_login()

            print("Fetching calendar entries...")
            calendar_entries = await self.get_calendar_entries(start_date, end_date)

            print(f"Found {len(calendar_entries.get('items', []))} calendar entries. Processing...")

            # Use the new method that fetches detailed lesson information including teachers
            lesson_list = await self.parse_calendar_entries_with_details(calendar_entries)

            if not lesson_list:
                print("Warning: No lessons were successfully processed")
            else:
                print("Sample lessons:")
                for i, lesson in enumerate(lesson_list[:3]):
                    print(f"  {i+1}. {lesson['subject']} at {lesson['from_date']} in {lesson['class_location']}")

            print(f"Successfully fetched {len(lesson_list)} lessons from Arbor")
            return lesson_list

        finally:
            await self.close_browser()


def get_cli_args() -> argparse.Namespace:
    """Get the command line arguments."""
    parser = argparse.ArgumentParser(
        description="Sync school calendar from Arbor API to Google Calendar"
    )
    parser.add_argument(
        "--start-date",
        help="The start date of the calendar in the format YYYY-MM-DD (defaults to academic year)",
    )
    parser.add_argument(
        "--end-date",
        help="The end date of the calendar in the format YYYY-MM-DD (defaults to academic year)",
    )
    parser.add_argument(
        "--academic-year",
        type=int,
        help="The academic year (YYYY) starting in September (defaults to current academic year)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run browser in headless mode (no GUI)",
    )
    parser.add_argument(
        "--calendar-id",
        help="Google Calendar ID to sync to (defaults to config or primary calendar)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without making changes",
    )
    return parser.parse_args()


async def main() -> None:
    """Main entry point."""
    args = get_cli_args()

    # Determine date range
    if args.start_date and args.end_date:
        try:
            start_date = datetime.datetime.strptime(args.start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(args.end_date, "%Y-%m-%d").date()
        except ValueError as e:
            print(f"Error parsing dates: {e}")
            return

        if start_date > end_date:
            print("Error: Start date must be before or equal to end date")
            return
    else:
        # Use academic year dates
        start_date, end_date = get_academic_year_dates(args.academic_year)
        print(f"Using academic year dates: {start_date} to {end_date}")

    # Fetch lessons from Arbor
    generator = ArborCalendarGenerator()
    lessons = await generator.fetch_lessons(start_date, end_date, headless=args.headless)

    if not lessons:
        print("No lessons found. Exiting.")
        return

    print(f"Fetched {len(lessons)} lessons from Arbor")

    # Print lesson summary
    print("\nLesson summary:")
    subjects = {}
    for lesson in lessons:
        subject = lesson["subject"]
        subjects[subject] = subjects.get(subject, 0) + 1

    for subject, count in sorted(subjects.items()):
        print(f"  {subject}: {count} lessons")

    # Import dependencies
    try:
        from config import config
        from google_calendar_sync import GoogleCalendarSync

        # Determine which calendar ID to use
        calendar_id = args.calendar_id if args.calendar_id else config.google_calendar_id

        # Sync with Google Calendar
        print(f"\nSyncing to Google Calendar '{calendar_id}'...")

        # Override config settings if provided via CLI
        if args.calendar_id:
            config.set("google_calendar.calendar_id", args.calendar_id)

        # Initialize Google Calendar sync
        calendar_sync = GoogleCalendarSync(calendar_id)

        # Authenticate with Google
        if not calendar_sync.authenticate():
            print("Failed to authenticate with Google Calendar.")
            print("Please run the setup script first:")
            print("  python setup_google_auth.py <path_to_credentials_file>")
            return

        # Perform the sync
        stats = calendar_sync.sync_events(lessons, dry_run=args.dry_run)

        if args.dry_run:
            print("Dry run completed - no actual changes were made")
        else:
            print("Sync completed successfully!")

        print(f"Events created: {stats['created']}")
        print(f"Events updated: {stats['updated']}")
        print(f"Events deleted: {stats['deleted']}")

    except ImportError as e:
        print(f"Failed to import required modules: {e}")
        print("Please install the required dependencies:")
        print("  uv sync")
    except Exception as e:
        print(f"Sync failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
