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
import logging
import os
from typing import Any

import bs4 as bs
import dateutil.tz
import icalendar
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from config import config

# Configure logging
logger = logging.getLogger(__name__)


def get_academic_year_dates(
    year: int | None = None,
) -> tuple[datetime.date, datetime.date]:
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
        if (
            hasattr(self, "context")
            and self.context
            and not getattr(self.context, "_closed", False)
        ):
            try:
                await self.context.close()
            except Exception:
                pass
        if hasattr(self, "browser") and self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass

        playwright = await async_playwright().start()

        # Debug: Show Playwright and browser information in Lambda
        if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            logger.debug("=== DEBUG: Playwright runtime information ===")
            logger.debug(
                f"   PLAYWRIGHT_BROWSERS_PATH: {os.environ.get('PLAYWRIGHT_BROWSERS_PATH', 'Not set')}"
            )
            logger.debug(
                f"   PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS: {os.environ.get('PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS', 'Not set')}"
            )

            # Check if browser binaries exist
            browsers_path = os.environ.get(
                "PLAYWRIGHT_BROWSERS_PATH", "/tmp/playwright-browsers"
            )
            if os.path.exists(browsers_path):
                logger.debug(f"   Browsers directory exists: {browsers_path}")

                # Find Chrome binaries using Python instead of find command
                chrome_binaries = []
                for root, _dirs, files in os.walk(browsers_path):
                    for file in files:
                        if "chrome" in file.lower():
                            full_path = os.path.join(root, file)
                            if os.path.isfile(full_path):
                                chrome_binaries.append(full_path)

                if chrome_binaries:
                    logger.debug(
                        f"   Chrome binaries found: {chr(10).join(chrome_binaries)}"
                    )
                else:
                    logger.debug("   No Chrome binaries found")
            else:
                logger.warning(f"   Browsers directory MISSING: {browsers_path}")
            logger.debug("==============================================")

        # Add Lambda-specific browser arguments with more aggressive resource reduction
        launch_args = []
        if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            launch_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-zygote",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-extensions",
                "--disable-default-apps",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-web-security",  # Add for Lambda environment
                "--disable-features=VizDisplayCompositor",  # Reduce memory usage
                "--memory-pressure-off",  # Disable memory pressure notifications
                "--max_old_space_size=2800",  # Limit Node.js memory (Lambda has 3072MB)
                "--disable-background-mode",
                "--disable-plugins",
                "--disable-images",  # Don't load images to save memory
                # Note: JavaScript is required for Arbor website interaction
                "--disable-accelerated-2d-canvas",  # Disable hardware acceleration
                "--disable-accelerated-jpeg-decoding",
                "--disable-accelerated-mjpeg-decode",
                "--disable-accelerated-video-decode",
                "--disable-3d-apis",  # Disable WebGL and 3D APIs
                "--disable-smooth-scrolling",
                "--disable-translate",
                "--disable-ipc-flooding-protection",  # May help with Lambda environment
                "--renderer-process-limit=1",  # Limit to single renderer process
                "--max-gum-fps=5",  # Limit frame rate
            ]

        # More conservative browser launch in Lambda with retry logic
        max_retries = 3 if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else 1
        for attempt in range(max_retries):
            try:
                self.browser = await playwright.chromium.launch(
                    headless=headless,
                    args=launch_args,
                    timeout=60000
                    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
                    else 30000,
                )
                break
            except Exception as e:
                logger.warning(f"   Browser launch attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"Failed to launch browser after {max_retries} attempts: {e}"
                    ) from e
                await asyncio.sleep(2)  # Wait before retry

        # Set longer timeout for Lambda environment
        browser_timeout = (
            120000 if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else 30000
        )

        # Retry context creation as well
        for attempt in range(max_retries):
            try:
                if not self.browser:
                    raise RuntimeError("Browser is None - cannot create context")

                if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
                    # Lambda-specific context with proper types
                    self.context = await self.browser.new_context(
                        ignore_https_errors=True,
                        extra_http_headers={
                            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        },
                        viewport={"width": 800, "height": 600},
                        java_script_enabled=True,
                        locale="en-US",
                    )
                else:
                    # Local context
                    self.context = await self.browser.new_context(
                        ignore_https_errors=True,
                        extra_http_headers={
                            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        },
                    )
                self.context.set_default_timeout(browser_timeout)
                self.page = await self.context.new_page()
                break
            except Exception as e:
                logger.warning(f"   Context creation attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"Failed to create browser context after {max_retries} attempts: {e}"
                    ) from e
                await asyncio.sleep(1)  # Wait before retry
        logger.info("✅ Browser started successfully")
        logger.debug(f"   Context created: {self.context is not None}")
        logger.debug(
            f"   Context closed status: {getattr(self.context, '_closed', 'unknown')}"
        )
        logger.debug(f"   Page created: {self.page is not None}")
        logger.debug(f"   Page closed: {self.page.is_closed() if self.page else 'N/A'}")

        # Test context immediately after creation
        try:
            if self.page:
                await self.page.evaluate("() => document.title")
                logger.debug("   ✓ Context validation: Page evaluation successful")
        except Exception as e:
            logger.error(f"   ❌ Context validation failed immediately: {e}")
            raise RuntimeError(
                f"Browser context failed validation immediately after creation: {e}"
            ) from e

    async def close_browser(self) -> None:
        """Close the browser and cleanup resources safely."""
        try:
            if hasattr(self, "page") and self.page and not self.page.is_closed():
                await self.page.close()
        except Exception as e:
            logger.warning(f"Error closing page: {e}")

        try:
            if (
                hasattr(self, "context")
                and self.context
                and not getattr(self.context, "_closed", False)
            ):
                await self.context.close()
        except Exception as e:
            logger.warning(f"Error closing context: {e}")

        try:
            if hasattr(self, "browser") and self.browser:
                await self.browser.close()
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")

        # Reset references
        self.page = None
        self.context = None
        self.browser = None

    async def interactive_login(self) -> None:
        """Perform interactive login to Arbor."""
        if not self.page:
            raise RuntimeError("Browser not started. Call start_browser() first.")

        # Check context before navigation with more detailed debugging
        if not self.context or getattr(self.context, "_closed", True):
            logger.critical(
                "❌ CRITICAL: Browser context validation failed before login"
            )
            logger.debug(f"   Context exists: {self.context is not None}")
            if self.context:
                logger.debug(
                    f"   Context closed: {getattr(self.context, '_closed', 'unknown')}"
                )
            logger.debug(f"   Page exists: {self.page is not None}")
            if self.page:
                logger.debug(f"   Page closed: {self.page.is_closed()}")

            # In Lambda, try to recreate the entire browser if context is closed
            if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
                logger.info(
                    "   Lambda environment detected - attempting full browser restart"
                )
                try:
                    # Close any remaining resources first
                    await self.close_browser()

                    # Restart the entire browser
                    logger.info("   Restarting browser due to context closure...")
                    await self.start_browser(headless=True)

                    if not self.page or not self.context:
                        raise RuntimeError(
                            "Failed to restart browser - context or page is None"
                        )

                    logger.info("   ✅ Browser restart successful")

                except Exception as recovery_error:
                    logger.error(f"   ❌ Browser restart failed: {recovery_error}")
                    raise RuntimeError(
                        f"Browser context was closed and recovery failed: {recovery_error}"
                    ) from recovery_error
            else:
                raise RuntimeError("Browser context was closed before login navigation")

        # Try base URL first since /auth/login might be broken
        logger.info(f"Navigating to Arbor base URL: {config.arbor_base_url}")

        # Increase timeout for initial navigation in Lambda
        navigation_timeout = (
            60000 if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else 30000
        )
        await self.page.goto(
            config.arbor_base_url, timeout=navigation_timeout, wait_until="networkidle"
        )
        logger.info("✅ Navigation to Arbor base URL completed")

        # Check context after navigation
        if not self.context or getattr(self.context, "_closed", True):
            raise RuntimeError("Browser context was closed during login navigation")

        # Add a small delay for stable page state
        await asyncio.sleep(2 if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else 1)

        # Check if we have credentials for automatic login
        username = config.arbor_username
        password = config.arbor_password

        if username and password:
            logger.info("Attempting automatic login with provided credentials...")
            try:
                await self._automatic_login(username, password)
                logger.info("Automatic login completed!")
            except Exception as e:
                logger.error(f"Automatic login failed: {e}")
                # Check if we're in Lambda environment - don't try manual login
                if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
                    logger.error(
                        "Running in Lambda environment, cannot perform manual login."
                    )
                    raise RuntimeError(
                        f"Automatic login failed in Lambda environment: {e}"
                    ) from e
                logger.info("Falling back to manual login...")
                await self._manual_login()
        else:
            # Check if we're in Lambda environment - don't try manual login
            if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
                logger.error("No credentials provided in Lambda environment.")
                raise RuntimeError(
                    "Cannot perform manual login in Lambda environment. Please provide ARBOR_USERNAME and ARBOR_PASSWORD."
                )
            logger.info("No credentials provided, using manual login...")
            await self._manual_login()

        # Verify we're logged in by checking for common elements
        try:
            await self.page.wait_for_selector(
                ".header, .navigation, .main-content", timeout=10000
            )
            logger.info("Login successful!")
        except Exception:
            logger.warning("Could not verify login status. Continuing anyway...")

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
            'input[id="username"]',
        ]

        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[id="password"]',
        ]

        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Log in")',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            ".login-button",
            ".btn-login",
        ]

        # Find and fill username field
        if not self.page:
            raise RuntimeError("Page not available")

        username_field = None
        for selector in login_selectors:
            try:
                username_field = await self.page.wait_for_selector(
                    selector, timeout=3000
                )
                if username_field:
                    break
            except Exception:
                continue

        if not username_field:
            raise RuntimeError("Could not find username field")

        # Find password field
        password_field = None
        for selector in password_selectors:
            try:
                password_field = await self.page.wait_for_selector(
                    selector, timeout=1000
                )
                if password_field:
                    break
            except Exception:
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
                submit_button = await self.page.wait_for_selector(
                    selector, timeout=1000
                )
                if submit_button:
                    break
            except Exception:
                continue

        if not submit_button:
            raise RuntimeError("Could not find submit button")

        # Submit the form
        await submit_button.click()

        # Wait for navigation after login
        try:
            if self.page:
                await self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            # If networkidle fails, wait a bit and continue
            await asyncio.sleep(3)

    async def _manual_login(self) -> None:
        """Perform manual login process."""
        logger.info("Please log in to Arbor in the browser window...")
        logger.info(
            "Press Enter once you have successfully logged in and are on the main page."
        )

        # Wait for user to complete login
        import sys

        if sys.stdin.isatty():
            try:
                input("Press Enter to continue after logging in...")
            except (EOFError, KeyboardInterrupt):
                logger.error("Login cancelled or failed.")
                raise
        else:
            logger.info(
                "Running in non-interactive mode, assuming login is completed..."
            )
            # Add a small delay to allow any auto-login to complete
            await asyncio.sleep(2)

    async def get_calendar_entries(
        self, start_date: datetime.date, end_date: datetime.date
    ) -> dict:
        """Get the calendar entries for the given date range."""
        if not self.page or self.page.is_closed():
            raise RuntimeError("Browser page is not available or has been closed.")

        if not self.context or getattr(self.context, "_closed", True):
            logger.critical(
                "❌ CRITICAL: Browser context is not available or has been closed."
            )
            logger.debug(f"   Context exists: {self.context is not None}")
            if self.context:
                logger.debug(
                    f"   Context closed: {getattr(self.context, '_closed', 'unknown')}"
                )
            logger.debug(f"   Page exists: {self.page is not None}")
            if self.page:
                logger.debug(f"   Page closed: {self.page.is_closed()}")
            logger.error(
                "   This suggests the browser was closed during operation or failed to initialize properly"
            )

            # Check if we're in Lambda - provide specific guidance
            if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
                logger.error(
                    "   Lambda environment detected - this may be a browser initialization issue"
                )
                logger.info(
                    "   Consider increasing Lambda timeout or checking browser launch arguments"
                )

            raise RuntimeError("Browser context is not available or has been closed.")

        # First navigate to the calendar page to establish session context
        calendar_page_url = f"{config.arbor_base_url}/calendar-entry/list/"
        logger.info(f"Navigating to calendar page: {calendar_page_url}")
        await self.page.goto(calendar_page_url)

        # Wait a moment for the page to load
        await asyncio.sleep(1)

        # Get the student object ID
        student_object_id = config.get("arbor.student_object_id", "7192")

        # Collect all calendar entries for the date range
        all_entries = []
        current_date = start_date

        logger.info(f"Fetching calendar entries from {start_date} to {end_date}")

        while current_date <= end_date:
            # Check if page is still valid before making request
            if not self.page or self.page.is_closed():
                logger.warning("Page was closed during calendar fetching, stopping...")
                break

            # Use the correct URL format: /date/YYYY-MM-DD (not query parameters)
            calendar_api_url = f"{config.arbor_base_url}/guardians/widget-data/get-calendar-data/student-id/{student_object_id}/date/{current_date}"

            try:
                response = await self.page.request.get(
                    calendar_api_url, timeout=30000
                )  # 30 second timeout

                if response.ok:
                    day_data = await response.json()
                    items = day_data.get("items", [])

                    if items:
                        logger.debug(f"  {current_date}: Found {len(items)} entries")
                        all_entries.extend(items)
                    else:
                        logger.debug(f"  {current_date}: No entries")
                else:
                    logger.warning(f"  {current_date}: HTTP Error {response.status}")

            except Exception as e:
                logger.error(f"  {current_date}: Error - {e}")

            # Move to next day
            current_date += datetime.timedelta(days=1)

            # Small delay to avoid overwhelming the API
            await asyncio.sleep(0.1)

        logger.info(f"Total entries found: {len(all_entries)}")

        # Return in the format expected by the rest of the code
        return {"items": all_entries, "success": True, "total": len(all_entries)}

    async def parse_calendar_entries_with_details(self, entries: dict) -> list[dict]:
        """
        Parse calendar entries and fetch detailed information including teacher data.
        For performance, we'll fetch detailed info for a sample of lessons first to test.
        """
        lessons: list[dict[str, Any]] = []

        if "items" not in entries or not isinstance(entries["items"], list):
            return lessons

        total_entries = len(entries["items"])
        logger.info(
            f"Fetching detailed information for a sample of {min(50, total_entries)} lessons to test teacher extraction..."
        )

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
                    logger.debug(
                        f"  Processed {i + 1}/{sample_size} detailed lessons..."
                    )

                # Small delay to avoid overwhelming the server
                await asyncio.sleep(0.2)

            except Exception as e:
                logger.warning(f"Failed to parse calendar entry {i + 1}: {e}")
                continue

        # For remaining lessons, just use basic extraction without detailed fetching
        if total_entries > sample_size:
            logger.info(
                f"Processing remaining {total_entries - sample_size} lessons with basic extraction..."
            )
            for item in entries["items"][sample_size:]:
                if not isinstance(item, dict) or "fields" not in item:
                    continue

                try:
                    # Only extract basic info for remaining lessons
                    basic_lesson = self.extract_basic_lesson_from_fields(item["fields"])
                    lessons.append(basic_lesson)
                except Exception as e:
                    logger.warning(f"Failed to parse basic calendar entry: {e}")
                    continue

        return lessons

    def extract_basic_lesson_from_fields(
        self, fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract basic lesson details from calendar entry fields."""

        # Extract the data from fields.{field_name}.value structure
        def get_field_value(field_name: str, default: Any = None) -> Any:
            field_data = fields.get(field_name, {})
            return field_data.get("value", default)

        # Debug: Print available fields on first few calls to understand structure
        if hasattr(self, "_debug_field_count"):
            self._debug_field_count += 1
        else:
            self._debug_field_count: int = 1

        if self._debug_field_count <= 3:
            logger.debug(f"Debug - Available fields: {list(fields.keys())}")
            for field_name, field_data in fields.items():
                if isinstance(field_data, dict) and "value" in field_data:
                    logger.debug(f"  {field_name}: {field_data['value']}")

        # Get the lesson title and extract subject
        title = get_field_value("title", "")
        # Title format is like: "Maths (KStg3): Year 9: 9X/Ma1"
        if ":" in title:
            subject = title.split(":")[0].strip()
            # Remove grade info in parentheses like "(KStg3)"
            if "(" in subject and ")" in subject:
                subject = subject.split("(")[0].strip()
        else:
            subject = title

        # Get location
        location = get_field_value("location")

        # Get date/time information
        start_datetime_str = get_field_value("start_datetime")
        end_datetime_str = get_field_value("end_datetime")

        if not start_datetime_str or not end_datetime_str:
            raise ValueError("Missing start or end datetime")

        # Parse datetime strings (format: "2025-09-16 08:30:00")
        try:
            from_date = datetime.datetime.strptime(
                start_datetime_str, "%Y-%m-%d %H:%M:%S"
            )
            to_date = datetime.datetime.strptime(end_datetime_str, "%Y-%m-%d %H:%M:%S")
        except ValueError as e:
            raise ValueError(f"Could not parse datetime: {e}") from e

        # Get the detail URL for fetching teacher information
        detail_url = get_field_value("url")

        return {
            "subject": subject,
            "class_location": location,
            "from_date": from_date,
            "to_date": to_date,
            "detail_url": detail_url,
            "staff": "Teacher TBD",  # Will be overridden by detailed fetch
        }

    async def get_detailed_lesson_info(self, detail_url: str) -> dict:
        """Fetch detailed lesson information including teacher from the lesson URL."""
        if not self.page or self.page.is_closed():
            logger.warning("Page is closed, cannot fetch detailed lesson info")
            return {"staff": "Teacher TBD"}

        if not self.context or getattr(self.context, "_closed", True):
            logger.warning(
                "Browser context is closed, cannot fetch detailed lesson info"
            )
            return {"staff": "Teacher TBD"}

        try:
            # Construct the full URL
            full_url = f"{config.arbor_base_url}{detail_url}"

            # Fetch the detailed lesson HTML
            response = await self.page.request.get(full_url)

            if not response.ok:
                logger.warning(
                    f"Failed to fetch lesson details from {full_url}: {response.status}"
                )
                return {"staff": "Teacher TBD"}

            html_content = await response.text()

            # Debug: Log HTML structure for first few requests to understand the format
            if hasattr(self, "_debug_html_count"):
                self._debug_html_count += 1
            else:
                self._debug_html_count: int = 1

            if self._debug_html_count <= 2:
                logger.debug(f"Debug HTML structure for URL {detail_url}:")
                logger.debug(f"HTML length: {len(html_content)} chars")
                logger.debug(f"HTML preview (first 500 chars): {html_content[:500]}")

            # Extract teacher information from HTML
            lesson_details = self.extract_lesson_details_new(html_content)

            return {"staff": lesson_details.get("staff", "Teacher TBD")}

        except Exception as e:
            logger.warning(f"Error fetching lesson details from {detail_url}: {e}")
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

        # Initialize result with defaults
        result = {
            "subject": "Unknown Subject",
            "class_location": None,
            "staff": "Teacher TBD",
            "from_date": None,
            "to_date": None,
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
                                    if (
                                        isinstance(prop_item, dict)
                                        and "props" in prop_item
                                    ):
                                        props = prop_item["props"]
                                        field_label = props.get(
                                            "fieldLabel", ""
                                        ).lower()
                                        value = props.get("value", "")

                                        # Debug: Print found properties
                                        if hasattr(self, "_debug_json_count"):
                                            self._debug_json_count += 1
                                        else:
                                            self._debug_json_count: int = 1

                                        if (
                                            self._debug_json_count <= 10
                                        ):  # Show more properties to understand structure
                                            logger.debug(
                                                f"Found property: '{field_label}' = '{value}'"
                                            )

                                        # Look for staff/teacher information
                                        if field_label in [
                                            "teacher",
                                            "staff",
                                            "tutor",
                                            "instructor",
                                            "taught by",
                                        ]:
                                            if value and value.strip():
                                                result["staff"] = value.strip()
                                                logger.debug(
                                                    f"Found staff in '{field_label}': {result['staff']}"
                                                )

                                        # Look for other common staff field names
                                        elif (
                                            "teacher" in field_label
                                            or "staff" in field_label
                                            or "tutor" in field_label
                                        ):
                                            if value and value.strip():
                                                result["staff"] = value.strip()
                                                logger.debug(
                                                    f"Found staff in '{field_label}': {result['staff']}"
                                                )

            # If still no staff found, try searching the entire JSON content as text
            if result["staff"] == "Teacher TBD":
                content_text = json.dumps(data).lower()

                # Look for teacher-related keywords in the JSON
                staff_keywords = ["teacher", "staff", "tutor", "instructor"]

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
                                    logger.debug(
                                        f"Found staff via JSON search with '{keyword}': {result['staff']}"
                                    )
                                    break

                        if result["staff"] != "Teacher TBD":
                            break

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse lesson detail JSON: {e}")
            # Fallback to treating it as HTML
            try:
                # This shouldn't happen based on what we've seen, but just in case
                # Could add HTML parsing fallback here if needed
                bs.BeautifulSoup(content, "html.parser")
            except Exception as fallback_e:
                logger.warning(f"Fallback HTML parsing also failed: {fallback_e}")

        except Exception as e:
            logger.error(f"Error parsing lesson details: {e}")

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
            from_date = datetime.datetime.strptime(
                f"{date_str} {from_time}", "%d %b %Y %H:%M"
            )
            to_date = datetime.datetime.strptime(
                f"{date_str} {to_time}", "%d %b %Y %H:%M"
            )
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
        cal.add(
            "prodid",
            config.get(
                "calendar.prod_id", "-//Tiffin School//Tiffin School Calendar//EN"
            ),
        )
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

            logger.info("Fetching calendar entries...")
            calendar_entries = await self.get_calendar_entries(start_date, end_date)

            logger.info(
                f"Found {len(calendar_entries.get('items', []))} calendar entries. Processing..."
            )

            # Use the new method that fetches detailed lesson information including teachers
            lesson_list = await self.parse_calendar_entries_with_details(
                calendar_entries
            )

            if not lesson_list:
                logger.warning("No lessons were successfully processed")
            else:
                logger.info("Sample lessons:")
                for i, lesson in enumerate(lesson_list[:3]):
                    logger.info(
                        f"  {i + 1}. {lesson['subject']} at {lesson['from_date']} in {lesson['class_location']}"
                    )

            logger.info(f"Successfully fetched {len(lesson_list)} lessons from Arbor")
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


def configure_logging() -> None:
    """Configure logging for the application."""
    # Get log level from environment variable or default to INFO
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )

    # Set appropriate log levels
    logging.getLogger(__name__).setLevel(logging.INFO)
    logging.getLogger("google_calendar_sync").setLevel(logging.INFO)


async def main() -> None:
    """Main entry point."""
    # Configure logging first
    configure_logging()

    args = get_cli_args()

    # Determine date range
    if args.start_date and args.end_date:
        try:
            start_date = datetime.datetime.strptime(args.start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(args.end_date, "%Y-%m-%d").date()
        except ValueError as e:
            logger.error(f"Error parsing dates: {e}")
            return

        if start_date > end_date:
            logger.error("Error: Start date must be before or equal to end date")
            return
    else:
        # Use academic year dates
        start_date, end_date = get_academic_year_dates(args.academic_year)
        logger.info(f"Using academic year dates: {start_date} to {end_date}")

    # Fetch lessons from Arbor
    generator = ArborCalendarGenerator()
    lessons = await generator.fetch_lessons(
        start_date, end_date, headless=args.headless
    )

    if not lessons:
        logger.error("No lessons found. Exiting.")
        return

    logger.info(f"Fetched {len(lessons)} lessons from Arbor")

    # Print lesson summary
    logger.info("\nLesson summary:")
    subjects: dict[str, int] = {}
    for lesson in lessons:
        subject = lesson["subject"]
        subjects[subject] = subjects.get(subject, 0) + 1

    for subject, count in sorted(subjects.items()):
        logger.info(f"  {subject}: {count} lessons")

    # Import dependencies
    try:
        from config import config
        from google_calendar_sync import GoogleCalendarSync

        # Determine which calendar ID to use
        calendar_id = (
            args.calendar_id if args.calendar_id else config.google_calendar_id
        )

        # Sync with Google Calendar
        logger.info(f"\nSyncing to Google Calendar '{calendar_id}'...")

        # Override config settings if provided via CLI
        if args.calendar_id:
            config.set("google_calendar.calendar_id", args.calendar_id)

        # Initialize Google Calendar sync
        calendar_sync = GoogleCalendarSync(calendar_id)

        # Authenticate with Google
        if not calendar_sync.authenticate():
            logger.error("Failed to authenticate with Google Calendar.")
            logger.error("Please run the setup script first:")
            logger.error("  python setup_google_auth.py <path_to_credentials_file>")
            return

        # Perform the sync
        stats = calendar_sync.sync_events(lessons, dry_run=args.dry_run)

        if args.dry_run:
            logger.info("Dry run completed - no actual changes were made")
        else:
            logger.info("Sync completed successfully!")

        logger.info(f"Events created: {stats['created']}")
        logger.info(f"Events updated: {stats['updated']}")
        logger.info(f"Events deleted: {stats['deleted']}")

    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        logger.error("Please install the required dependencies:")
        logger.error("  uv sync")
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
