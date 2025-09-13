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
- **Dual Deployment**: Run locally as a script OR deploy as AWS Lambda with weekly scheduling
- **AWS Integration**: CloudFormation template with EventBridge for automated weekly syncs
- **CI/CD Pipeline**: GitHub Actions workflow for automated testing and deployment

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

### 4. Run the Application

#### Local Script Mode

```bash
# Sync current academic year (local mode uses full year)
uv run python lambda_handler.py

# Preview changes without applying them
uv run python lambda_handler.py --dry-run

# Sync specific date range
uv run python lambda_handler.py --start-date 2024-01-01 --end-date 2024-07-31

# Run in headless mode (no browser window)
uv run python lambda_handler.py --headless
```

#### AWS Lambda Deployment

**Option 1: GitHub Actions (Recommended)**

For automated deployment on every push to main:

1. Set up GitHub repository secrets (see [.github/DEPLOYMENT.md](.github/DEPLOYMENT.md))
2. Push to main branch - deployment happens automatically
3. Monitor deployment in GitHub Actions tab

**Option 2: Manual SAM Deployment**

For manual deployment using SAM CLI:

```bash
# Build and deploy with SAM CLI
sam build
sam deploy --guided
```

The deployment includes:
- Lambda function with 15-minute timeout
- EventBridge schedule for weekly execution (Sundays at 8 AM UTC)
- IAM roles and policies for Parameter Store access
- CloudWatch log group for monitoring

See [deployment/README.md](deployment/README.md) for detailed manual AWS deployment instructions.

## Usage Options

### Local Script Mode

```bash
python lambda_handler.py [OPTIONS]

Options:
  --start-date DATE        Start date (YYYY-MM-DD), defaults to academic year
  --end-date DATE          End date (YYYY-MM-DD), defaults to academic year
  --academic-year YEAR     Academic year starting in September (e.g., 2024)
  --headless               Run browser in headless mode (no GUI)
  --dry-run                Show what would be synced without making changes
```

### AWS Lambda Mode

**Automated Deployment (GitHub Actions):**
- Push to main branch triggers automatic deployment
- Tests run first, then builds and deploys if tests pass
- Deployment tested automatically with dry-run invocation

**Manual Deployment (SAM CLI):**
```bash
sam build
sam deploy --guided
```

Lambda runs automatically every Sunday at 8 AM UTC with these features:
- Headless browser mode (no GUI)
- Environment-based configuration from AWS Parameter Store
- CloudWatch logging and monitoring
- Weekly EventBridge schedule
- Optimized date range (syncs only future events from today to end of academic year)

## How It Works

1. **Execution Mode Detection**: Automatically detects local vs Lambda execution mode
2. **Credential Management**: Loads from .env file locally or AWS Parameter Store in Lambda
3. **Smart Date Range**: Uses full academic year locally, optimized future-only range in Lambda
4. **Authentication**: Automatic login to Arbor using configured credentials or manual browser login
5. **Data Fetching**: Uses correct Arbor API endpoint (`/guardians/widget-data/get-calendar-data/student-id/{id}/date/{date}`) to fetch calendar entries
6. **Data Processing**: Parses new nested field structure (`fields.{field}.value`) and extracts lesson details
7. **Event Creation**: Converts lessons to Google Calendar events with embedded Arbor IDs in descriptions
8. **Smart Sync**: Compares with existing events using Arbor IDs, prevents duplicates
9. **Rate-Limited Sync**: Applies changes with proper rate limiting for large datasets (1,291+ lessons)

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
# GOOGLE_TOKEN_PATH=./token.json  # Auto-generated during OAuth flow

# Arbor Configuration
ARBOR_BASE_URL=https://your-school.uk.arbor.sc
ARBOR_TIMEZONE=Europe/London
ARBOR_STUDENT_OBJECT_ID=1234
ARBOR_USERNAME=your.username@example.com
ARBOR_PASSWORD=your-password

# AWS Lambda Configuration (Optional - for Parameter Store integration)
# GOOGLE_CREDENTIALS_PARAMETER=/arbor-calendar-sync/google-credentials
# GOOGLE_TOKEN_PARAMETER=/arbor-calendar-sync/google-token
# ARBOR_USERNAME_PARAMETER=/arbor-calendar-sync/arbor-username
# ARBOR_PASSWORD_PARAMETER=/arbor-calendar-sync/arbor-password
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

### Local Development

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

### Automated CI/CD

The project includes a GitHub Actions workflow that automatically:

1. **On every push/PR**: Runs tests, linting, and type checking
2. **On push to main**: Builds and deploys to AWS Lambda
3. **Tests deployment**: Verifies Lambda deployment with dry-run invocation

Setup instructions: [.github/DEPLOYMENT.md](.github/DEPLOYMENT.md)

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
- Verify the ARBOR_STUDENT_OBJECT_ID is correct for your student account
- Ensure your Google Calendar ID is correct (should end in @group.calendar.google.com for shared calendars)

### Browser Issues
- Use `--headless` flag if you have display issues
- Ensure Playwright browsers are installed: `uv run playwright install`
- For SSL certificate issues, the app automatically ignores HTTPS errors

### Data Issues
- Check that you're using the correct Arbor base URL for your school
- Verify the student object ID matches your Arbor account

### AWS Lambda Issues

For Lambda deployment issues, check:
- CloudWatch logs: `/aws/lambda/your-function-name`
- Environment variables are properly configured
- Lambda execution role has necessary permissions
- Function timeout (default: 15 minutes) is sufficient
- See [deployment/README.md](deployment/README.md) for detailed troubleshooting

## Deployment Options

### Local Development
Perfect for testing and manual syncs:
```bash
python lambda_handler.py --dry-run
```

### AWS Lambda (Recommended)
Automated weekly syncs with no maintenance:
- Deploy once with SAM CLI using included CloudFormation template
- Runs every Sunday at 8 AM UTC automatically via EventBridge
- Secure credential storage in AWS Parameter Store
- CloudWatch monitoring and logging with 15-minute timeout
- Optimized execution (syncs only future events from today)
- No server management required
- Cost: ~$0/month (within AWS free tier)

See [deployment/README.md](deployment/README.md) for complete AWS setup instructions.