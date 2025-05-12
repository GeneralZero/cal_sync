import caldav
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import logging
from difflib import SequenceMatcher

from config import (
    CALDAV_URL, CALDAV_USERNAME, CALDAV_PASSWORD,
    CONFIRMED_CALENDAR, POSSIBLE_CALENDAR, DEDUP_THRESHOLD
)
from event_source import Event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CalendarSync:
    def __init__(self):
        self.client = caldav.DAVClient(
            url=CALDAV_URL,
            username=CALDAV_USERNAME,
            password=CALDAV_PASSWORD
        )
        self.principal = self.client.principal()
        self._confirmed_calendar = None
        self._possible_calendar = None

    def _get_or_create_calendar(self, calendar_name: str) -> caldav.Calendar:
        """Get or create a calendar with the given name."""
        calendars = self.principal.calendars()
        for calendar in calendars:
            if calendar.name == calendar_name:
                return calendar
        
        return self.principal.make_calendar(name=calendar_name)

    @property
    def confirmed_calendar(self) -> caldav.Calendar:
        if not self._confirmed_calendar:
            self._confirmed_calendar = self._get_or_create_calendar(CONFIRMED_CALENDAR)
        return self._confirmed_calendar

    @property
    def possible_calendar(self) -> caldav.Calendar:
        if not self._possible_calendar:
            self._possible_calendar = self._get_or_create_calendar(POSSIBLE_CALENDAR)
        return self._possible_calendar

    def _event_to_ical(self, event: Event) -> str:
        """Convert our Event object to iCal format."""
        # Ensure times are in UTC
        start_time = event.start_time.astimezone(timezone.utc)
        end_time = event.end_time.astimezone(timezone.utc)
        
        ical_template = f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:{event.title}
DTSTART:{start_time.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end_time.strftime('%Y%m%dT%H%M%SZ')}
"""
        if event.description:
            # Escape newlines and commas in description
            description = event.description.replace('\n', '\\n').replace(',', '\\,')
            ical_template += f"DESCRIPTION:{description}\n"
        if event.location:
            # Escape newlines and commas in location
            location = event.location.replace('\n', '\\n').replace(',', '\\,')
            ical_template += f"LOCATION:{location}\n"
        if event.url:
            ical_template += f"URL:{event.url}\n"
        
        # Add custom properties for source tracking
        if event.source:
            ical_template += f"X-EVENT-SOURCE:{event.source}\n"
        if event.source_id:
            ical_template += f"X-SOURCE-ID:{event.source_id}\n"

        ical_template += """END:VEVENT
END:VCALENDAR"""
        return ical_template

    def _is_duplicate(self, event: Event, existing_events: List[caldav.Event], threshold: float = DEDUP_THRESHOLD) -> bool:
        
        for existing in existing_events:
            event_summary = existing.icalendar_component.get("summary")
            event_time = existing.icalendar_component.get("dtstart").dt

            # Ensure event_time is a datetime with timezone info
            if isinstance(event_time, datetime):
                event_time = event_time.astimezone(timezone.utc)
            else:
                event_time = datetime.combine(event_time, datetime.min.time(), tzinfo=timezone.utc)

            if (
                abs((event.start_time - event_time).total_seconds()) < 3600 and
                SequenceMatcher(None, event.title, event_summary).ratio() > threshold
            ):
                return True
        return False

        
    async def sync_events(self, events: List[Event]):
        """Sync events to the appropriate calendars."""
        for event in events:
            try:
                if event.is_confirmed:
                    target_calendar = self.confirmed_calendar
                    other_calendar = self.possible_calendar
                else:
                    target_calendar = self.possible_calendar
                    other_calendar = self.confirmed_calendar
                
                # Get existing events in a time window around this event
                time_window = timedelta(days=1)
                start = event.start_time - time_window
                end = event.start_time + time_window
                
                # Use calendar.search() instead of date_search()
                existing_events = target_calendar.search(
                    start=start,
                    end=end,
                    event=True,
                    expand=True
                )
                #logger.info(f"Found {len(existing_events)} existing events in the time window")

                # Remove duplicates from the other calendar
                other_existing_events = other_calendar.search(
                    start=start,
                    end=end,
                    event=True,
                    expand=True
                )

                #logger.info(f"Testing for duplicates in {event.title}")
                #Delete duplicates from the other calendar
                for existing in other_existing_events:
                    if self._is_duplicate(event, [existing]):
                        logger.info(f"Deleting duplicate event from {other_calendar.name}: {event.title}")
                        existing.delete()

                # Skip if it's a duplicate
                if self._is_duplicate(event, existing_events):
                    logger.info(f"Skipping duplicate event: {event.title}")
                    continue

                #logger.info(f"Before Add event: {event.title}")
                # Add the event
                ical_data = self._event_to_ical(event)
                target_calendar.save_event(ical_data)
                logger.info(f"Added event: {event.title} to {target_calendar.name}")

            except Exception as e:
                logger.error(f"Error syncing event {event.title}: {str(e)}")
