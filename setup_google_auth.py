#!/usr/bin/env python3
"""Setup script for Google Calendar API authentication."""

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from config import config

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def print_instructions() -> None:
    """Print setup instructions for Google Cloud Console."""
    print("=" * 60)
    print("Google Calendar API Setup Instructions")
    print("=" * 60)
    print()
    print("Before running this script, you need to set up Google Calendar API access:")
    print()
    print("1. Go to the Google Cloud Console: https://console.cloud.google.com/")
    print("2. Create a new project or select an existing one")
    print("3. Enable the Google Calendar API:")
    print("   - Go to 'APIs & Services' > 'Library'")
    print("   - Search for 'Google Calendar API'")
    print("   - Click on it and press 'Enable'")
    print()
    print("4. Create credentials:")
    print("   - Go to 'APIs & Services' > 'Credentials'")
    print("   - Click '+ CREATE CREDENTIALS' > 'OAuth client ID'")
    print("   - Choose 'Desktop application' as the application type")
    print("   - Give it a name (e.g., 'Arbor Calendar Sync')")
    print("   - Click 'Create'")
    print()
    print("5. Download the credentials:")
    print("   - Click the download button (⬇) for your OAuth client")
    print("   - Save the file as 'client_secrets.json'")
    print()
    print("6. Run this script again with the path to your credentials file")
    print()
    print("=" * 60)


def validate_credentials_file(credentials_path: Path) -> bool:
    """
    Validate the credentials file format.

    Args:
        credentials_path: Path to credentials file

    Returns:
        True if valid, False otherwise
    """
    if not credentials_path.exists():
        print(f"Error: Credentials file not found at {credentials_path}")
        return False

    try:
        with open(credentials_path, encoding="utf-8") as f:
            creds_data = json.load(f)

        # Check if it's the right format
        if "installed" not in creds_data and "web" not in creds_data:
            print("Error: Invalid credentials file format.")
            print("Make sure you downloaded the OAuth client ID credentials, not a service account key.")
            return False

        client_data = creds_data.get("installed") or creds_data.get("web")
        required_fields = ["client_id", "client_secret", "auth_uri", "token_uri"]

        for field in required_fields:
            if field not in client_data:
                print(f"Error: Missing required field '{field}' in credentials file.")
                return False

        print("✓ Credentials file format is valid")
        return True

    except json.JSONDecodeError:
        print("Error: Credentials file is not valid JSON.")
        return False
    except Exception as e:
        print(f"Error reading credentials file: {e}")
        return False


def setup_authentication(credentials_path: Path) -> bool:
    """
    Set up Google Calendar authentication.

    Args:
        credentials_path: Path to Google credentials file

    Returns:
        True if setup successful, False otherwise
    """
    if not validate_credentials_file(credentials_path):
        return False

    try:
        # Copy credentials to config directory
        config_credentials_path = config.credentials_path
        config_credentials_path.parent.mkdir(parents=True, exist_ok=True)

        if credentials_path != config_credentials_path:
            print(f"Copying credentials to {config_credentials_path}")
            with open(credentials_path, encoding="utf-8") as src:
                credentials_content = src.read()
            with open(config_credentials_path, "w", encoding="utf-8") as dst:
                dst.write(credentials_content)

        # Run OAuth flow
        print("\nStarting OAuth authentication flow...")
        print("A browser window will open for you to authenticate with Google.")
        print("Please grant access to your Google Calendar.")

        flow = InstalledAppFlow.from_client_secrets_file(str(config_credentials_path), SCOPES)
        creds = flow.run_local_server(port=0)

        # Save the token
        token_path = config.token_path
        token_path.parent.mkdir(parents=True, exist_ok=True)

        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

        print("✓ Authentication successful!")
        print(f"✓ Token saved to {token_path}")
        print(f"✓ Credentials saved to {config_credentials_path}")

        # Test the authentication
        print("\nTesting Google Calendar access...")
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        service = build("calendar", "v3", credentials=creds)

        try:
            # Test by getting calendar list
            calendars_result = service.calendarList().list(maxResults=10).execute()
            calendars = calendars_result.get("items", [])

            print(f"✓ Successfully connected! Found {len(calendars)} calendars:")
            for i, calendar in enumerate(calendars[:5]):  # Show first 5
                cal_id = calendar["id"]
                cal_name = calendar.get("summary", "No name")
                primary = " (PRIMARY)" if calendar.get("primary") else ""
                print(f"  {i+1}. {cal_name}{primary}")
                if i == 0:  # Show ID for primary calendar
                    print(f"     Calendar ID: {cal_id}")

            if len(calendars) > 5:
                print(f"     ... and {len(calendars) - 5} more")

        except HttpError as e:
            print(f"✗ Failed to access Google Calendar: {e}")
            return False

        print("\n" + "=" * 60)
        print("Setup Complete!")
        print("=" * 60)
        print("You can now run the main script to sync your Arbor calendar:")
        print("  python generate_school_calendar.py")
        print()
        print("Or use the installed command:")
        print("  arbor-calendar-sync")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"Setup failed: {e}")
        return False


def main() -> None:
    """Main setup function."""
    print("Arbor Calendar Sync - Google Authentication Setup")
    print()

    if len(sys.argv) < 2:
        print_instructions()
        print("\nUsage: python setup_google_auth.py <path_to_credentials_file>")
        print("Example: python setup_google_auth.py ./client_secrets.json")
        sys.exit(1)

    credentials_path = Path(sys.argv[1])

    if not setup_authentication(credentials_path):
        print("\nSetup failed. Please check the errors above and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
