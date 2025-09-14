"""Unit tests for the school calendar generator."""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from generate_school_calendar import ArborCalendarGenerator, get_academic_year_dates


@pytest.fixture
def generator():
    """Create a calendar generator instance for testing."""
    return ArborCalendarGenerator()


@pytest.fixture
def sample_html():
    """Sample HTML response from Arbor calendar tooltip."""
    return """
    <div class="header">
        <div class="title">Mathematics: Year 10</div>
    </div>
    <div class="content">
        <ul>
            <li><span>Monday, 15 Jan 2024, 09:00 - 10:00</span></li>
            <li><span>Location: Room 101</span></li>
            <li><span>Mr. Smith</span></li>
        </ul>
    </div>
    """


@pytest.fixture
def sample_html_no_location():
    """Sample HTML response without location information."""
    return """
    <div class="header">
        <div class="title">English: Year 9</div>
    </div>
    <div class="content">
        <ul>
            <li><span>Tuesday, 16 Jan 2024, 10:00 - 11:00</span></li>
            <li><span>Ms. Johnson</span></li>
        </ul>
    </div>
    """


@pytest.fixture
def sample_calendar_entries():
    """Sample calendar entries response from Arbor API."""
    return {
        "items": [
            {
                "fields": {
                    "response": {
                        "value": {
                            "pages": [
                                {
                                    "html": 'Some content ajax-link="/tooltip/1" more content ajax-link="/tooltip/2" end'
                                }
                            ]
                        }
                    }
                }
            }
        ]
    }


class TestArborCalendarGenerator:
    """Test cases for ArborCalendarGenerator class."""

    @pytest.mark.asyncio
    async def test_start_and_close_browser(self, generator):
        """Test browser startup and cleanup."""
        with patch(
            "generate_school_calendar.async_playwright"
        ) as mock_async_playwright:
            mock_playwright_instance = AsyncMock()
            mock_async_playwright.return_value = mock_playwright_instance

            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()

            # Set up is_closed as a regular method, not async
            mock_page.is_closed = MagicMock(return_value=False)

            mock_playwright_instance.start.return_value = mock_playwright_instance
            mock_playwright_instance.chromium.launch.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page

            await generator.start_browser(headless=True)

            assert generator.browser is mock_browser
            assert generator.context is mock_context
            assert generator.page is mock_page

            mock_playwright_instance.start.assert_called_once()
            mock_playwright_instance.chromium.launch.assert_called_once_with(
                headless=True, args=[]
            )
            mock_browser.new_context.assert_called_once_with(
                ignore_https_errors=True,
                extra_http_headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
            )
            mock_context.new_page.assert_called_once()

            await generator.close_browser()
            mock_context.close.assert_called_once()
            mock_browser.close.assert_called_once()

    def test_get_calendar_html(self, generator, sample_calendar_entries):
        """Test parsing calendar HTML for AJAX links."""
        links = generator.get_calendar_html(sample_calendar_entries)

        assert links == ["/tooltip/1", "/tooltip/2"]

    def test_get_calendar_html_no_links(self, generator):
        """Test parsing calendar HTML with no AJAX links."""
        entries = {
            "items": [
                {
                    "fields": {
                        "response": {
                            "value": {"pages": [{"html": "No ajax links here"}]}
                        }
                    }
                }
            ]
        }

        links = generator.get_calendar_html(entries)
        assert links == []

    def test_extract_lesson_details(self, generator, sample_html):
        """Test extraction of lesson details from HTML."""
        details = generator.extract_lesson_details(sample_html)

        expected = {
            "subject": "Mathematics",
            "class_location": "Room 101",
            "staff": "Mr. Smith",
            "from_date": datetime.datetime(2024, 1, 15, 9, 0),
            "to_date": datetime.datetime(2024, 1, 15, 10, 0),
        }

        assert details == expected

    def test_extract_lesson_details_no_location(
        self, generator, sample_html_no_location
    ):
        """Test extraction when location is not provided."""
        details = generator.extract_lesson_details(sample_html_no_location)

        expected = {
            "subject": "English",
            "class_location": None,
            "staff": "Ms. Johnson",
            "from_date": datetime.datetime(2024, 1, 16, 10, 0),
            "to_date": datetime.datetime(2024, 1, 16, 11, 0),
        }

        assert details == expected

    def test_extract_lesson_details_invalid_html(self, generator):
        """Test extraction with invalid HTML."""
        invalid_html = "<div>Invalid HTML structure</div>"

        with pytest.raises(ValueError, match="Could not find lesson title"):
            generator.extract_lesson_details(invalid_html)

    def test_extract_lesson_details_insufficient_details(self, generator):
        """Test extraction with insufficient lesson details."""
        insufficient_html = """
        <div class="header">
            <div class="title">Mathematics: Year 10</div>
        </div>
        <div class="content">
            <ul>
                <li><span>Monday, 15 Jan 2024, 09:00 - 10:00</span></li>
            </ul>
        </div>
        """

        with pytest.raises(ValueError, match="Insufficient lesson details"):
            generator.extract_lesson_details(insufficient_html)

    def test_extract_lesson_details_invalid_date_format(self, generator):
        """Test extraction with invalid date format."""
        invalid_date_html = """
        <div class="header">
            <div class="title">Mathematics: Year 10</div>
        </div>
        <div class="content">
            <ul>
                <li><span>Invalid date format</span></li>
                <li><span>Location: Room 101</span></li>
                <li><span>Mr. Smith</span></li>
            </ul>
        </div>
        """

        with pytest.raises(ValueError, match="Could not parse date/time"):
            generator.extract_lesson_details(invalid_date_html)

    def test_create_calendar_event(self, generator):
        """Test creation of iCalendar event."""
        lesson = {
            "subject": "Mathematics",
            "class_location": "Room 101",
            "staff": "Mr. Smith",
            "from_date": datetime.datetime(2024, 1, 15, 9, 0),
            "to_date": datetime.datetime(2024, 1, 15, 10, 0),
        }

        event = generator.create_calendar_event(lesson)

        assert event["summary"] == "Mathematics"
        assert event["location"] == "Room 101"
        assert event["description"] == "Mr. Smith"

    def test_create_calendar(self, generator):
        """Test creation of complete calendar."""
        lessons = [
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

        calendar = generator.create_calendar(lessons)

        assert calendar["prodid"] == "-//Tiffin School//Tiffin School Calendar//EN"
        assert calendar["version"] == "2.0"
        assert len(calendar.subcomponents) == 2

    @pytest.mark.asyncio
    async def test_interactive_login_no_browser(self, generator):
        """Test interactive login without browser started."""
        with pytest.raises(RuntimeError, match="Browser not started"):
            await generator.interactive_login()

    @pytest.mark.asyncio
    async def test_get_calendar_entries_no_browser(self, generator):
        """Test getting calendar entries without browser started."""
        start_date = datetime.date(2024, 1, 1)
        end_date = datetime.date(2024, 1, 31)

        with pytest.raises(RuntimeError, match="Browser not started"):
            await generator.get_calendar_entries(start_date, end_date)

    @pytest.mark.asyncio
    async def test_get_calendar_entry_no_browser(self, generator):
        """Test getting calendar entry without browser started."""
        with pytest.raises(RuntimeError, match="Browser not started"):
            await generator.get_calendar_entry("/tooltip/1")

    @pytest.mark.asyncio
    async def test_get_calendar_entries_with_mock_request(self, generator):
        """Test getting calendar entries with mocked request."""
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_response = AsyncMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "items": [{"test": "data"}],
            "success": True,
            "total": 1,
        }

        # Set up page methods
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.request.get.return_value = mock_response
        mock_page.goto = AsyncMock()

        # Set up context
        mock_context._closed = False

        generator.page = mock_page
        generator.context = mock_context

        start_date = datetime.date(2024, 1, 1)
        end_date = datetime.date(2024, 1, 31)

        result = await generator.get_calendar_entries(start_date, end_date)

        assert result == {"items": [{"test": "data"}], "success": True, "total": 1}
        # Should call goto once for calendar page navigation
        mock_page.goto.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_calendar_entries_request_failure(self, generator):
        """Test handling of failed calendar request."""
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_response = AsyncMock()
        mock_response.ok = False
        mock_response.status = 500

        # Set up page methods
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.request.get.return_value = mock_response
        mock_page.goto = AsyncMock()

        # Set up context
        mock_context._closed = False

        generator.page = mock_page
        generator.context = mock_context

        start_date = datetime.date(2024, 1, 1)
        end_date = datetime.date(2024, 1, 31)

        with pytest.raises(RuntimeError, match="Failed to fetch calendar entries: 500"):
            await generator.get_calendar_entries(start_date, end_date)

    @pytest.mark.asyncio
    async def test_get_calendar_entry_with_mock_request(self, generator):
        """Test getting individual calendar entry with mocked request."""
        mock_page = AsyncMock()
        mock_response = AsyncMock()
        mock_response.ok = True
        mock_response.text.return_value = "<html>Test response</html>"

        mock_page.request.get.return_value = mock_response
        generator.page = mock_page

        result = await generator.get_calendar_entry("/tooltip/1")

        assert result == "<html>Test response</html>"
        from config import config

        mock_page.request.get.assert_called_once_with(
            f"{config.arbor_base_url}/tooltip/1"
        )

    @pytest.mark.asyncio
    async def test_get_calendar_entry_request_failure(self, generator):
        """Test handling of failed calendar entry request."""
        mock_page = AsyncMock()
        mock_response = AsyncMock()
        mock_response.ok = False
        mock_response.status = 404

        mock_page.request.get.return_value = mock_response
        generator.page = mock_page

        with pytest.raises(RuntimeError, match="Failed to fetch calendar entry: 404"):
            await generator.get_calendar_entry("/tooltip/1")


class TestAcademicYearDates:
    """Test cases for academic year date calculation."""

    def test_get_academic_year_dates_with_year(self):
        """Test getting academic year dates with specific year."""
        start_date, end_date = get_academic_year_dates(2024)

        assert start_date == datetime.date(2024, 9, 1)
        assert end_date == datetime.date(2025, 7, 31)

    def test_get_academic_year_dates_auto_september(self):
        """Test automatic year detection in September."""
        with patch("generate_school_calendar.datetime") as mock_datetime:
            # Mock date but preserve datetime functionality for creating dates
            mock_datetime.date.side_effect = lambda *args: datetime.date(*args)
            mock_datetime.date.today = MagicMock(
                return_value=datetime.date(2024, 9, 15)
            )

            start_date, end_date = get_academic_year_dates()

            assert start_date == datetime.date(2024, 9, 1)
            assert end_date == datetime.date(2025, 7, 31)

    def test_get_academic_year_dates_auto_january(self):
        """Test automatic year detection in January (previous academic year)."""
        with patch("generate_school_calendar.datetime") as mock_datetime:
            # Mock date but preserve datetime functionality for creating dates
            mock_datetime.date.side_effect = lambda *args: datetime.date(*args)
            mock_datetime.date.today = MagicMock(
                return_value=datetime.date(2025, 1, 15)
            )

            start_date, end_date = get_academic_year_dates()

            assert start_date == datetime.date(2024, 9, 1)
            assert end_date == datetime.date(2025, 7, 31)

    def test_get_academic_year_dates_auto_august(self):
        """Test automatic year detection in August (previous academic year)."""
        with patch("generate_school_calendar.datetime") as mock_datetime:
            # Mock date but preserve datetime functionality for creating dates
            mock_datetime.date.side_effect = lambda *args: datetime.date(*args)
            mock_datetime.date.today = MagicMock(
                return_value=datetime.date(2024, 8, 15)
            )

            start_date, end_date = get_academic_year_dates()

            assert start_date == datetime.date(2023, 9, 1)
            assert end_date == datetime.date(2024, 7, 31)
