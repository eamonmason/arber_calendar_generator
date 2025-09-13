# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python application that syncs school calendar events from the Arbor API directly to Google Calendar using Playwright for web automation. It provides automatic or manual login with Arbor, automatically fetches the full UK academic year (1,291+ lessons), and intelligently synchronizes events with conflict resolution and duplicate prevention.

## Dependencies and Environment

- Uses uv for dependency and environment management
- Python 3.11+
- Key dependencies: playwright, beautifulsoup4, icalendar, google-api-python-client, google-auth, python-dateutil, python-dotenv
- Development dependencies include pytest, ruff, mypy for testing and linting
- Environment configuration via .env files with python-dotenv

## Development Commands

```bash
# Install dependencies
uv sync

# Install Playwright browsers
uv run playwright install

# Set up Google Calendar authentication
python setup_google_auth.py <credentials_file>

# Run the sync (full academic year)
uv run python generate_school_calendar.py

# Preview changes without applying
uv run python generate_school_calendar.py --dry-run

# Sync specific date range
uv run python generate_school_calendar.py --start-date 2024-01-01 --end-date 2024-07-31

# Use installed command
arbor-calendar-sync

# Run linting
uv run ruff check
uv run ruff format

# Run type checking
uv run mypy .

# Run tests
uv run pytest
```

## Code Architecture

The application follows a modular design with three main components:

### Core Modules:

1. **`generate_school_calendar.py`** - Main application and Arbor integration
   - `ArborCalendarGenerator` class handles Arbor API interaction via correct endpoint format
   - `get_academic_year_dates()` - Calculates UK academic year dates
   - Automatic login with credentials from .env or fallback to manual login
   - New API endpoint: `/guardians/widget-data/get-calendar-data/student-id/{id}/date/{date}`
   - Direct parsing of new nested field structure (`fields.{field}.value`)
   - Main CLI interface and workflow orchestration

2. **`google_calendar_sync.py`** - Google Calendar integration
   - `GoogleCalendarSync` class handles Google Calendar API
   - OAuth2 authentication and token management
   - Event reconciliation with embedded Arbor IDs (not event IDs due to Google restrictions)
   - Rate limiting for large datasets (1,291+ lessons)
   - Duplicate prevention and proper update handling
   - Uses event descriptions to store and track Arbor IDs

3. **`config.py`** - Configuration management
   - `Config` class for centralized settings with environment variable support
   - .env file integration with python-dotenv
   - JSON-based fallback configuration with sensible defaults
   - Environment variables take precedence over JSON config
   - User-specific config directory management

4. **`setup_google_auth.py`** - Interactive authentication setup
   - Guides users through Google Cloud Console setup
   - OAuth2 flow with credential validation
   - Authentication testing and troubleshooting

### Main Flow:
1. **Date Calculation** (`get_academic_year_dates()`) - Auto-calculate academic year dates
2. **Environment Loading** - Load configuration from .env file with python-dotenv
3. **Arbor Authentication** - Automatic login with stored credentials or manual browser login
4. **Arbor Data Fetching** (`get_calendar_entries()`) - Uses correct API endpoint with date path format
5. **Data Processing** (`parse_calendar_entries_direct()`) - Parse new nested field structure
6. **Event Processing** - Convert Arbor lessons to Google Calendar events with embedded IDs
7. **Google Authentication** (`GoogleCalendarSync.authenticate()`) - Google Calendar API authentication
8. **Event Reconciliation** (`reconcile_events()`) - Smart comparison using embedded Arbor IDs
9. **Rate-Limited Synchronization** (`sync_events()`) - Apply changes with rate limiting and duplicate prevention

### Key Features:
- **Academic Year Support**: Automatic September-July date calculation (1,291+ lessons)
- **Flexible Authentication**: Stored credentials for Arbor automation or manual login, OAuth2 for Google
- **Smart Sync**: Creates, updates, and deletes events based on embedded Arbor IDs
- **Duplicate Prevention**: Uses event descriptions to track Arbor IDs and prevent duplicates
- **Rate Limiting**: Handles large syncs with proper API rate limiting
- **Conflict Resolution**: Handles existing events intelligently
- **Dry Run Mode**: Preview changes before applying
- **Environment Configuration**: Secure .env file configuration with precedence over JSON
- **SSL Certificate Handling**: Automatically ignores HTTPS errors for school systems

## Key Configuration

Environment variables (via .env file):
- `GOOGLE_CALENDAR_ID`: Target Google Calendar ID (e.g., `abc123@group.calendar.google.com`)
- `GOOGLE_CREDENTIALS_PATH`: Path to Google OAuth2 credentials JSON file
- `ARBOR_BASE_URL`: Arbor system URL (e.g., `https://tiffin-school.uk.arbor.sc`)
- `ARBOR_STUDENT_OBJECT_ID`: Student object ID for API calls (e.g., `7192`)
- `ARBOR_USERNAME`: Optional username for automatic login
- `ARBOR_PASSWORD`: Optional password for automatic login
- `ARBOR_TIMEZONE`: Europe/London timezone for all events

Fallback configuration:
- Config file: `~/.config/arbor-calendar-sync/config.json`
- Google credentials: `~/.config/arbor-calendar-sync/credentials.json`

## Data Flow

1. **Arbor Authentication**: Uses Playwright with automatic or manual login
2. **API Data Fetching**: Calls correct Arbor guardian widget API with date-based path format
3. **Data Processing**: Parses new nested field structure (`fields.{field_name}.value`)
4. **Event Generation**: Creates Google Calendar events with embedded Arbor IDs in descriptions
5. **Reconciliation**: Compares with existing events using Arbor IDs extracted from descriptions
6. **Rate-Limited Operations**: Applies changes with proper rate limiting and duplicate prevention

## Unique ID Strategy

Events are tracked using stable hash-based IDs embedded in descriptions:
- Hash input: `subject|from_date|staff|location`
- Prefix: `arbor_` for easy identification
- Stored in event description as `ID: arbor_{hash}` since Google doesn't allow custom event IDs
- Ensures consistent tracking across sync runs for proper event reconciliation
- Prevents duplicate creation by matching existing events via description parsing

## Testing

- **Main Module Tests**: `test_generate_school_calendar.py` - Core functionality and academic year logic
- **Sync Module Tests**: `test_google_calendar_sync.py` - Google Calendar integration and reconciliation
- Comprehensive mocking of external APIs
- Tests cover error cases, edge cases, and async functionality
- Run with `uv run pytest` - all tests should pass

## Google Calendar Integration

- Uses OAuth2 for secure authentication
- Supports batch operations for efficiency
- Event reconciliation prevents duplicates
- Configurable sync behavior (create/update/delete)
- Proper timezone handling and metadata

## Security Notes

- Optional credential storage for Arbor in .env files for automation (with secure file permissions)
- OAuth2 tokens stored securely in user config directory
- All operations use official Google APIs
- Local-only data processing (no external services)
- SSL certificate bypass for school systems with self-signed certificates
- Environment variables take precedence for secure configuration management