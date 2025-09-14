#!/usr/bin/env python3
"""
AWS Lambda handler for Arbor Calendar Sync.

This module provides both Lambda function entry point and local script execution.
Can be run locally or deployed as a Lambda function with EventBridge scheduling.

Usage:
    # Run locally
    python lambda_handler.py

    # Deploy to AWS Lambda
    # See deployment/README.md for instructions
"""

import asyncio
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from generate_school_calendar import ArborCalendarGenerator, get_academic_year_dates
from google_calendar_sync import GoogleCalendarSync


def get_parameter_from_aws(parameter_name: str) -> Any:
    """Retrieve parameter from AWS Systems Manager Parameter Store."""
    try:
        import boto3
        from botocore.exceptions import ClientError

        ssm_client = boto3.client("ssm")
        print(f"Attempting to get parameter: {parameter_name}")
        response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)

        # For JSON parameters, parse the value
        parameter_value = response["Parameter"]["Value"]
        print(
            f"Successfully retrieved parameter {parameter_name} (length: {len(parameter_value)})"
        )
        try:
            return json.loads(parameter_value)
        except json.JSONDecodeError:
            # Return as string if not JSON
            return parameter_value
    except ImportError:
        # boto3 not available (local execution)
        print(f"boto3 not available for parameter {parameter_name}")
        return None
    except ClientError as e:
        print(f"ClientError retrieving parameter {parameter_name}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error retrieving parameter {parameter_name}: {e}")
        return None


def setup_aws_credentials() -> None:
    """Set up credentials from AWS Parameter Store if running in Lambda."""
    # Check if we're running in AWS Lambda
    if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return  # Not in Lambda, use local credentials

    print("Running in AWS Lambda, retrieving credentials from Parameter Store...")

    # AWS credentials are validated when we actually call GetParameter below
    print("✓ AWS Lambda environment detected, will use Parameter Store")

    # Track what credentials we successfully load
    credentials_loaded = {
        "google_credentials": False,
        "google_token": False,
        "arbor_username": False,
        "arbor_password": False,
    }

    # Create temporary directory for credential files
    temp_dir = Path(tempfile.mkdtemp())

    # Get Google credentials
    google_creds_param = os.environ.get("GOOGLE_CREDENTIALS_PARAMETER")
    if google_creds_param:
        google_creds = get_parameter_from_aws(google_creds_param)
        if google_creds:
            credentials_path = temp_dir / "credentials.json"
            with open(credentials_path, "w") as f:
                json.dump(google_creds, f)
            os.environ["GOOGLE_CREDENTIALS_PATH"] = str(credentials_path)
            print("✓ Google credentials loaded from Parameter Store")
            credentials_loaded["google_credentials"] = True

    # Get Google token
    google_token_param = os.environ.get("GOOGLE_TOKEN_PARAMETER")
    if google_token_param:
        google_token = get_parameter_from_aws(google_token_param)
        if google_token:
            token_path = temp_dir / "token.json"
            with open(token_path, "w") as f:
                json.dump(google_token, f)
            os.environ["GOOGLE_TOKEN_PATH"] = str(token_path)
            print("✓ Google token loaded from Parameter Store")
            credentials_loaded["google_token"] = True

    # Get Arbor username
    arbor_username_param = os.environ.get("ARBOR_USERNAME_PARAMETER")
    print(f"Looking for Arbor username parameter: {arbor_username_param}")
    if arbor_username_param:
        arbor_username = get_parameter_from_aws(arbor_username_param)
        if arbor_username:
            os.environ["ARBOR_USERNAME"] = arbor_username
            print("✓ Arbor username loaded from Parameter Store")
            credentials_loaded["arbor_username"] = True
        else:
            print(f"❌ Failed to load Arbor username from {arbor_username_param}")
    else:
        print("❌ ARBOR_USERNAME_PARAMETER environment variable not set")

    # Get Arbor password
    arbor_password_param = os.environ.get("ARBOR_PASSWORD_PARAMETER")
    print(f"Looking for Arbor password parameter: {arbor_password_param}")
    if arbor_password_param:
        arbor_password = get_parameter_from_aws(arbor_password_param)
        if arbor_password:
            os.environ["ARBOR_PASSWORD"] = arbor_password
            print("✓ Arbor password loaded from Parameter Store")
            credentials_loaded["arbor_password"] = True
        else:
            print(f"❌ Failed to load Arbor password from {arbor_password_param}")
    else:
        print("❌ ARBOR_PASSWORD_PARAMETER environment variable not set")

    # Summary of credential loading
    print(f"\n📋 Credential loading summary: {credentials_loaded}")

    # Check if we have the minimum required credentials for operation
    if (
        not credentials_loaded["arbor_username"]
        or not credentials_loaded["arbor_password"]
    ):
        missing = [k for k, v in credentials_loaded.items() if not v and "arbor" in k]
        error_msg = f"Missing required Arbor credentials: {missing}. Cannot proceed with calendar sync."
        print(f"❌ {error_msg}")
        raise RuntimeError(error_msg)


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """
    AWS Lambda entry point for scheduled calendar sync.

    Args:
        event: Lambda event data (from EventBridge scheduler)
        context: Lambda context object

    Returns:
        Dict with execution results
    """
    try:
        print("Starting Arbor Calendar Sync Lambda execution...")
        print(f"Event: {json.dumps(event, default=str)}")

        # Set up AWS credentials (if running in Lambda)
        setup_aws_credentials()

        # Extract parameters from event (EventBridge can pass custom data)
        dry_run = bool(event.get("dry_run", False))
        headless = bool(event.get("headless", True))  # Always headless in Lambda
        academic_year_val = event.get("academic_year")
        academic_year = (
            int(academic_year_val) if academic_year_val is not None else None
        )
        start_date_val = event.get("start_date")
        start_date = str(start_date_val) if start_date_val is not None else None
        end_date_val = event.get("end_date")
        end_date = str(end_date_val) if end_date_val is not None else None

        # Run the sync
        result = asyncio.run(
            run_calendar_sync(
                dry_run=dry_run,
                headless=headless,
                academic_year=academic_year,
                start_date=start_date,
                end_date=end_date,
            )
        )

        print("Lambda execution completed successfully")
        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Calendar sync completed successfully",
                    "result": result,
                    "timestamp": datetime.datetime.now().isoformat(),
                }
            ),
        }

    except Exception as e:
        print(f"Lambda execution failed: {e}")
        import traceback

        traceback.print_exc()

        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "error": str(e),
                    "message": "Calendar sync failed",
                    "timestamp": datetime.datetime.now().isoformat(),
                }
            ),
        }


async def run_calendar_sync(
    dry_run: bool = False,
    headless: bool = True,
    academic_year: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    Run the calendar sync operation.

    Args:
        dry_run: Whether to run in dry-run mode
        headless: Whether to run browser in headless mode
        academic_year: Academic year to sync (optional)
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)

    Returns:
        Dict with sync results
    """
    print("Determining date range...")

    # Determine date range
    if start_date and end_date:
        try:
            sync_start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            sync_end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError as e:
            raise ValueError(f"Error parsing dates: {e}") from e

        if sync_start_date > sync_end_date:
            raise ValueError("Start date must be before or equal to end date")
    else:
        # Use current date to end of academic year for Lambda efficiency
        if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            # In Lambda: sync from today to end of current academic year
            today = datetime.date.today()
            _, academic_year_end = get_academic_year_dates(academic_year)
            sync_start_date = today
            sync_end_date = academic_year_end

            # Handle case where we're past the academic year end
            if sync_start_date > sync_end_date:
                print(
                    f"Current date ({today}) is past academic year end ({academic_year_end})"
                )
                print("No future events to sync. Exiting.")
                return {
                    "lessons_found": 0,
                    "events_created": 0,
                    "events_updated": 0,
                    "events_deleted": 0,
                    "message": "Current date is past academic year end - no future events to sync",
                }

            print(
                f"Lambda mode: Syncing from today ({sync_start_date}) to end of academic year ({sync_end_date})"
            )
        else:
            # Local execution: use full academic year dates
            sync_start_date, sync_end_date = get_academic_year_dates(academic_year)
            print(
                f"Local mode: Using full academic year dates: {sync_start_date} to {sync_end_date}"
            )

    # Fetch lessons from Arbor
    print("Initializing Arbor calendar generator...")
    generator = ArborCalendarGenerator()
    lessons = await generator.fetch_lessons(
        sync_start_date, sync_end_date, headless=headless
    )

    if not lessons:
        print("No lessons found. Exiting.")
        return {
            "lessons_found": 0,
            "events_created": 0,
            "events_updated": 0,
            "events_deleted": 0,
            "message": "No lessons found",
        }

    print(f"Fetched {len(lessons)} lessons from Arbor")

    # Print lesson summary
    print("Lesson summary:")
    subjects: dict[str, int] = {}
    for lesson in lessons:
        subject = lesson["subject"]
        subjects[subject] = subjects.get(subject, 0) + 1

    for subject, count in sorted(subjects.items()):
        print(f"  {subject}: {count} lessons")

    # Sync with Google Calendar
    calendar_id = config.google_calendar_id
    print(f"Syncing to Google Calendar '{calendar_id}'...")

    # Initialize Google Calendar sync
    calendar_sync = GoogleCalendarSync(calendar_id)

    # Authenticate with Google
    if not calendar_sync.authenticate():
        raise RuntimeError(
            "Failed to authenticate with Google Calendar. Please check credentials."
        )

    # Perform the sync
    stats = calendar_sync.sync_events(lessons, dry_run=dry_run)

    if dry_run:
        print("Dry run completed - no actual changes were made")
    else:
        print("Sync completed successfully!")

    result = {
        "lessons_found": len(lessons),
        "events_created": stats["created"],
        "events_updated": stats["updated"],
        "events_deleted": stats["deleted"],
        "dry_run": dry_run,
        "date_range": f"{sync_start_date} to {sync_end_date}",
        "subjects": subjects,
    }

    print(f"Events created: {stats['created']}")
    print(f"Events updated: {stats['updated']}")
    print(f"Events deleted: {stats['deleted']}")

    return result


def main() -> None:
    """
    Main entry point for local script execution.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Arbor Calendar Sync - Local execution mode"
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
        "--dry-run",
        action="store_true",
        help="Show what would be synced without making changes",
    )

    args = parser.parse_args()

    print("Running Arbor Calendar Sync locally...")

    try:
        result = asyncio.run(
            run_calendar_sync(
                dry_run=args.dry_run,
                headless=args.headless,
                academic_year=args.academic_year,
                start_date=args.start_date,
                end_date=args.end_date,
            )
        )

        print("\n" + "=" * 50)
        print("SYNC SUMMARY")
        print("=" * 50)
        print(f"Lessons found: {result['lessons_found']}")
        print(f"Events created: {result['events_created']}")
        print(f"Events updated: {result['events_updated']}")
        print(f"Events deleted: {result['events_deleted']}")
        print(f"Date range: {result['date_range']}")
        if result["dry_run"]:
            print("Mode: DRY RUN (no changes made)")
        print("=" * 50)

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
