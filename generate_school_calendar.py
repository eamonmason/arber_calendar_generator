"""
Generate a school calendar from the Arbor API.

This script logs into the Arbor API, retrieves the calendar entries for a given
date range, and creates an iCalendar file from the lessons.

Usage: python generate_school_calendar.py <username> <password> <start_date> <end_date>
"""

# flake8: noqa E501

import argparse
import datetime
import json
import tempfile

import boto3
import bs4 as bs
import dateutil.tz
import icalendar
import requests

CALENDAR_BASE_URL = 'https://tiffin-school.uk.arbor.sc'
LOGIN_URL = f'{CALENDAR_BASE_URL}/auth/login'
CALENDAR_URL = f'{CALENDAR_BASE_URL}/calendar-entry/list-static/format/json/'
BUCKET_NAME = 'feed.tobiasmasonvanes.com'
FILENAME = 'tiffin-calendar.ics'
TIMEZONE = "Europe/London"
CALENDAR_PROD_ID = "-//Tiffin School//Tiffin School Calendar//EN"


def authenticate(username: str, password: str) -> requests.cookies.RequestsCookieJar:
    """Authenticate with the Arbor API and return the cookies"""
    response = requests.post(
        LOGIN_URL,
        headers={'Content-Type': 'application/json'},
        data=json.dumps(
            {'items': [{'username': username, 'password': password}]}),
        timeout=10)
    response.raise_for_status()
    return response.cookies


def get_calendar_entries(
        cookies: requests.cookies.RequestsCookieJar,
        start_date: datetime.date,
        end_date: datetime.date) -> dict:
    """Get the calendar entries for the given date range"""
    response = requests.post(
        CALENDAR_URL,
        headers={'Content-Type': 'application/json'},
        cookies=cookies,
        data=json.dumps({
            'action_params': {
                'view': 'period',
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
                'filters': [
                    {'field_name': 'object', 'value': {'_objectTypeId': 1, '_objectId': 7192}}]
            }
        }),
        timeout=30)
    response.raise_for_status()
    return response.json()


def get_cli_args():
    """Get the command line arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument('username', help='The username to authenticate with')
    parser.add_argument('password', help='The password to authenticate with')
    parser.add_argument(
        'start_date', help='The start date of the calendar in the format YYYY-MM-DD')
    parser.add_argument(
        'end_date', help='The end date of the calendar in the format YYYY-MM-DD')
    return parser.parse_args()


def get_calendar_html(entries):
    """Parse the calendar entries from the response JSON, under items, fields,
    response, value, pages list"""
    ajax_link_list = []
    for h in entries['items'][0]['fields']['response']['value']['pages']:
        if 'html' in h:
            for link in h['html'].split('ajax-link="')[1:]:
                ajax_link_list.append(link.split('"')[0])
    return ajax_link_list


def get_calendar_entry(tooltip_url: str, cookies: requests.cookies.RequestsCookieJar) -> dict:
    """Get the calendar entry details for the given tooltip URL"""
    response = requests.get(
        f'{CALENDAR_BASE_URL}{tooltip_url}',
        cookies=cookies,
        timeout=30)
    response.raise_for_status()
    return response.text


def extract_lesson_details(html: str) -> dict:
    """Extract the lesson details from the HTML"""
    parser = bs.BeautifulSoup(html, 'html.parser')
    subject = parser.select_one('.header > .title').text.split(': Year')[0]
    lesson_details = parser.select('.content > ul > li')
    if len(lesson_details) < 3:
        class_location = None
        staff = lesson_details[1].select_one('span').text
    else:
        class_location = lesson_details[1].select_one(
            'span').text.split(':')[1].strip()
        staff = lesson_details[2].select_one('span').text
    source_date = lesson_details[0].select_one('span').text.replace('\n', '')
    parsed_date = ' '.join(source_date.split())
    date_str, time_str = parsed_date.split(', ')[1:]
    from_time, to_time = time_str.split(' - ')
    from_date = datetime.datetime.strptime(
        f'{date_str} {from_time}', '%d %b %Y %H:%M')
    to_date = datetime.datetime.strptime(
        f'{date_str} {to_time}', '%d %b %Y %H:%M')
    return {
        'subject': subject,
        'class_location': class_location,
        'staff': staff,
        'from_date': from_date,
        'to_date': to_date}


def create_calendar_event(lesson: dict) -> icalendar.Event:
    """Create an iCalendar event from the lesson details"""
    e = icalendar.Event()
    tz = dateutil.tz.tzstr(TIMEZONE)
    e.add('summary', lesson['subject'])
    e.add('location', lesson['class_location'])
    e.add('description', lesson['staff'])
    e.add('dtstart', lesson['from_date'].astimezone(tz))
    e.add('dtend', lesson['to_date'].astimezone(tz))
    return e


def create_calendar(lesson_list: list) -> icalendar.Calendar:
    """Create an iCalendar from the list of lessons"""
    cal = icalendar.Calendar()
    cal.add('prodid', CALENDAR_PROD_ID)
    cal.add('version', '2.0')
    for lesson in lesson_list:
        cal.add_component(create_calendar_event(lesson))
    return cal


def upload_ical_to_s3(ical_calendar: icalendar.Calendar):
    """Upload the iCalendar to S3"""
    s3_client = boto3.client('s3')
    try:
        temp_file = tempfile.TemporaryFile()
        temp_file.write(ical_calendar.to_ical())
        temp_file.seek(0)
        s3_client.upload_fileobj(temp_file, BUCKET_NAME, FILENAME)
    except Exception as e:
        print(f"Failed to upload file to S3: {e}")
    finally:
        temp_file.close()


def _main():
    args = get_cli_args()
    start_date = datetime.datetime.strptime(args.start_date, '%Y-%m-%d').date()
    end_date = datetime.datetime.strptime(args.end_date, '%Y-%m-%d').date()
    cookies = authenticate(args.username, args.password)
    calendar_entries = get_calendar_entries(cookies, start_date, end_date)
    links = get_calendar_html(calendar_entries)
    lesson_list = []
    for link in links:
        tooltip_response = get_calendar_entry(link, cookies)
        lesson_details = extract_lesson_details(tooltip_response)
        lesson_list.append(lesson_details)
    ical_calendar = create_calendar(lesson_list)
    upload_ical_to_s3(ical_calendar)


if __name__ == '__main__':
    _main()
