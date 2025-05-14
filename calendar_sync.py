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

	def _remove_duplicate_events(self, event: Event, calendar: caldav.Calendar) -> int:
		"""Remove all duplicate instances of the event from the given calendar.
		Returns the number of events removed."""
		count = 0
		time_window = timedelta(days=1)
		start = event.start_time - time_window
		end = event.start_time + time_window
		
		# Search for potential duplicates
		potential_duplicates = calendar.search(
			start=start,
			end=end,
			event=True,
			expand=True
		)
		
		# Remove all duplicates
		for existing in potential_duplicates:
			event_summary = existing.icalendar_component.get("summary")
			event_time = existing.icalendar_component.get("dtstart").dt
			
			# Ensure event_time is a datetime with timezone info
			if isinstance(event_time, datetime):
				event_time = event_time.astimezone(timezone.utc)
			else:
				event_time = datetime.combine(event_time, datetime.min.time(), tzinfo=timezone.utc)
			
			if (
				abs((event.start_time - event_time).total_seconds()) < 3600 and
				SequenceMatcher(None, event.title, event_summary).ratio() > DEDUP_THRESHOLD
			):
				try:
					existing.delete()
					count += 1
				except Exception as e:
					logger.error(f"Error deleting duplicate event '{event_summary}': {str(e)}")
		
		return count

	async def sync_events(self, events: List[Event]):
		"""Sync events to the appropriate calendars."""
		for event in events:
			try:              
				# Get existing events in a time window around this event
				time_window = timedelta(days=1)
				start = event.start_time - time_window
				end = event.start_time + time_window
				
				# Use calendar.search() instead of date_search()
				confirmed_events = self.confirmed_calendar.search(
					start=start,
					end=end,
					event=True,
					expand=True
				)

				# Get events from the other calendar
				possible_events = self.possible_calendar.search(
					start=start,
					end=end,
					event=True,
					expand=True
				)

				if event.is_confirmed:
					# It's a confirmed event - remove it from possible_calendar if it exists there
					removed_count = self._remove_duplicate_events(event, self.possible_calendar)
					if removed_count > 0:
						logger.info(f"Removed {removed_count} instances of '{event.title}' from {self.possible_calendar.name}")
					
					# Check if it already exists in confirmed_calendar
					if self._is_duplicate(event, confirmed_events):
						logger.info(f"Event already exists in {self.confirmed_calendar.name}: {event.title}")
						continue
					
					# Add to confirmed_calendar
					ical_data = self._event_to_ical(event)
					self.confirmed_calendar.save_event(ical_data)
					logger.info(f"Added confirmed event: {event.title} to {self.confirmed_calendar.name}")
				else:
					# It's not a confirmed event - check if it's already in confirmed_calendar
					if self._is_duplicate(event, confirmed_events):
						logger.info(f"Skipping event '{event.title}' - appears to be manually moved to {self.confirmed_calendar.name}")
						continue
					
					# Check for duplicates in possible_calendar
					if self._is_duplicate(event, possible_events):
						logger.info(f"Duplicate event found in {self.possible_calendar.name}: {event.title}")
						continue
					
					# Add to possible_calendar
					ical_data = self._event_to_ical(event)
					self.possible_calendar.save_event(ical_data)
					logger.info(f"Added possible event: {event.title} to {self.possible_calendar.name}")

			except Exception as e:
				logger.error(f"Error syncing event {event.title}: {str(e)}")
