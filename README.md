# Arbor Calendar Sync

Sync school calendar events from the Arbor API directly to Google Calendar using Playwright for web automation.

## Features

- **Automatic Login**: Configurable automatic login with stored credentials or manual browser-based authentication
- **Google Calendar Integration**: Direct synchronization with named Google Calendar
- **Academic Year Support**: Automatically fetches full UK academic year (September-July) - 1,291+ lessons
- **Smart Sync**: Creates, updates, and deletes events as needed with duplicate prevention
- **Conflict Resolution**: Handles existing events intelligently using embedded Arbor IDs
- **Rate Limiting**: Handles large syncs with proper API rate limiting
- **Dry Run Mode**: Preview changes before applying them
- **Environment Configuration**: Secure configuration via .env files

## Quick Start

### 1. Install Dependencies

```bash
uv sync
uv run playwright install
```

### 2. Configure Environment

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Edit `.env` to set your configuration:

```bash
# Google Calendar Configuration
GOOGLE_CALENDAR_ID=your-calendar-id@group.calendar.google.com
GOOGLE_CREDENTIALS_PATH=./path/to/credentials.json

# Arbor Configuration
ARBOR_BASE_URL=https://your-school.uk.arbor.sc
ARBOR_STUDENT_OBJECT_ID=1234
ARBOR_USERNAME=your.username@example.com
ARBOR_PASSWORD=your-password
```

### 3. Set Up Google Calendar API

First, you'll need to:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create/select a project and enable Google Calendar API
3. Create OAuth2 credentials for a desktop application
4. Download the credentials JSON file

Then run the setup script:

```bash
uv run python setup_google_auth.py <path_to_credentials_file>
```

### 4. Sync Your Calendar

```bash
# Sync current academic year
uv run python generate_school_calendar.py

# Preview changes without applying them
uv run python generate_school_calendar.py --dry-run

# Sync specific date range
uv run python generate_school_calendar.py --start-date 2024-01-01 --end-date 2024-07-31

# Use installed command
arbor-calendar-sync
```

## Usage Options

```bash
arbor-calendar-sync [OPTIONS]

Options:
  --start-date DATE        Start date (YYYY-MM-DD), defaults to academic year
  --end-date DATE          End date (YYYY-MM-DD), defaults to academic year
  --academic-year YEAR     Academic year starting in September (e.g., 2024)
  --calendar-id ID         Google Calendar ID (defaults to primary)
  --headless               Run browser in headless mode (no GUI)
  --dry-run                Show what would be synced without making changes
```

## How It Works

1. **Authentication**: Automatic login to Arbor using configured credentials or manual browser login
2. **Data Fetching**: Uses correct Arbor API endpoint (`/guardians/widget-data/get-calendar-data/student-id/{id}/date/{date}`) to fetch calendar entries
3. **Data Processing**: Parses new nested field structure (`fields.{field}.value`) and extracts lesson details
4. **Event Creation**: Converts lessons to Google Calendar events with embedded Arbor IDs in descriptions
5. **Smart Sync**: Compares with existing events using Arbor IDs, prevents duplicates
6. **Rate-Limited Sync**: Applies changes with proper rate limiting for large datasets (1,291+ lessons)

## Configuration

### Environment Variables (.env file)

The easiest way to configure the application is using environment variables. Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

Key environment variables:

```bash
# Google Calendar Configuration
GOOGLE_CALENDAR_ID=your-calendar-id@group.calendar.google.com
GOOGLE_CREDENTIALS_PATH=./client_secret_*.json
# GOOGLE_TOKEN_PATH is auto-generated during OAuth flow

# Arbor Configuration
ARBOR_BASE_URL=https://your-school.uk.arbor.sc
ARBOR_TIMEZONE=Europe/London
ARBOR_STUDENT_OBJECT_ID=1234
ARBOR_USERNAME=your.username@example.com
ARBOR_PASSWORD=your-password

# Sync Behavior (Optional)
# SYNC_DELETE_ORPHANED_EVENTS=true
# SYNC_UPDATE_EXISTING_EVENTS=true
# SYNC_DRY_RUN=false
```

### JSON Configuration (Alternative)

Configuration can also be stored in `~/.config/arbor-calendar-sync/config.json`:

```json
{
  "google_calendar": {
    "calendar_id": "primary",
    "credentials_path": "~/.config/arbor-calendar-sync/credentials.json"
  },
  "sync": {
    "delete_orphaned_events": true,
    "update_existing_events": true,
    "batch_size": 100
  },
  "arbor": {
    "timezone": "Europe/London",
    "calendar_base_url": "https://your-school.uk.arbor.sc"
  }
}
```

**Note**: Environment variables take precedence over JSON configuration.

## Development

```bash
# Run tests
uv run pytest

# Run linting
uv run ruff check
uv run ruff format

# Run type checking
uv run mypy .

# Run all checks
uv run pytest && uv run ruff check && uv run mypy .
```

## Security Notes

- **Environment Variables**: Store sensitive configuration in `.env` files (never commit these to version control)
- **Credentials**: OAuth2 credentials are stored locally and never transmitted
- **Authentication**: Uses OAuth2 for secure Google Calendar access
- **Arbor Credentials**: Optional automatic login with encrypted storage in `.env` files
- **Data Privacy**: All data stays on your machine, no external services
- **File Permissions**: Ensure `.env` and credential files have restricted permissions (`chmod 600`)

### Protecting Sensitive Files

```bash
# Set secure permissions
chmod 600 .env
chmod 600 ~/.config/arbor-calendar-sync/credentials.json
chmod 600 ~/.config/arbor-calendar-sync/token.json

# Verify .env is in .gitignore
echo ".env" >> .gitignore
```

## Troubleshooting

### Authentication Issues
- Run `uv run python setup_google_auth.py` again with fresh credentials
- Check that Google Calendar API is enabled in your project
- Verify OAuth2 consent screen is configured
- For Arbor login issues, try manual login (remove ARBOR_USERNAME/PASSWORD from .env)

### Sync Issues
- Use `--dry-run` to see what changes would be made
- Check calendar permissions in Google Calendar settings
- Get your calendar ID by running `uv run python list_calendars.py`
- Verify the ARBOR_STUDENT_OBJECT_ID is correct for your student account

### Browser Issues
- Use `--headless` flag if you have display issues
- Ensure Playwright browsers are installed: `uv run playwright install`
- For SSL certificate issues, the app automatically ignores HTTPS errors

### Data Issues
- Check that you're using the correct Arbor base URL for your school
- Verify the student object ID matches your Arbor account
- Use debug scripts (`debug_event_ids.py`, `test_correct_url_format.py`) for troubleshooting