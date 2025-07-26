import caldav
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import logging, traceback
from difflib import SequenceMatcher
from ics import Calendar as ICSCalendar
from ics.event import Event as ICSEvent

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

		ical_template += "STATUS:CONFIRMED\n" if event.is_confirmed else "STATUS:TENTATIVE\n"

		
		# Add custom properties for source tracking
		if event.source:
			ical_template += f"X-EVENT-SOURCE:{event.source}\n"
		if event.source_id:
			ical_template += f"X-SOURCE-ID:{event.source_id}\n"

		ical_template += """END:VEVENT
END:VCALENDAR"""
		return ical_template

	def _duplicate_events_ics(self, event: Event, existing_events: List[caldav.Event], threshold: float = DEDUP_THRESHOLD) -> bool:
		duplicate_events = []

		for existing in existing_events:
			event_summary = existing.icalendar_component.get("summary")
			event_time = existing.icalendar_component.get("dtstart").dt

			# Ensure event_time is a datetime with timezone info
			if isinstance(event_time, datetime):
				event_time = event_time.astimezone(timezone.utc)
			else:
				event_time = datetime.combine(event_time, datetime.min.time(), tzinfo=timezone.utc)

			if (
				abs((event.begin - event_time).total_seconds()) < 3600 and
				SequenceMatcher(None, event.name, event_summary).ratio() > threshold
			):
				duplicate_events.append(existing)

		return duplicate_events

	def _duplicate_events(self, event: Event, existing_events: List[caldav.Event], threshold: float = DEDUP_THRESHOLD) -> bool:
		duplicate_events = []
		for existing in existing_events:
			event_summary = existing.icalendar_component.get("summary")
			event_time = existing.icalendar_component.get("dtstart").dt
			if isinstance(event, ICSEvent):
				event_start = event.begin.astimezone(timezone.utc)
				event_title = event.name
			else:
				event_start = event.start_time.astimezone(timezone.utc)
				event_title = event.title

			# Ensure event_time is a datetime with timezone info
			if isinstance(event_time, datetime):
				event_time = event_time.astimezone(timezone.utc)
			else:
				event_time = datetime.combine(event_time, datetime.min.time(), tzinfo=timezone.utc)

			if (
				abs((event_start - event_time).total_seconds()) < 3600 and
				SequenceMatcher(None, event_title, event_summary).ratio() > threshold
			):
				duplicate_events.append(existing)
		
		return duplicate_events
	
	def _event_properties_changed(self, event: Event, existing_event: caldav.Event) -> bool:
		for prop in event.__dict__:
			logger.info(f"Checking property {prop} for changes")
			if prop not in existing_event.icalendar_component:
				logger.info(f"Property {prop} not found in existing event. Event has changed.")
				return True
			if existing_event.icalendar_component[prop] != event.__dict__[prop]:
				logger.info(f"Property {prop} has changed from {existing_event.icalendar_component[prop]} to {event.__dict__[prop]}.")
				return True
		return False

	def _remove_duplicate_events(self, event: Event, calendar: caldav.Calendar) -> int:
		"""Remove all duplicate instances of the event from the given calendar.
		Returns the number of events removed."""
		count = 0
		time_window = timedelta(days=1)

		if isinstance(event, ICSEvent):
			start = event.begin - time_window
			end = event.begin + time_window
			event_title = event.name
			event_start = event.begin.astimezone(timezone.utc)
		else:
			start = event.start_time - time_window
			end = event.start_time + time_window
			event_title = event.title
			event_start = event.start_time.astimezone(timezone.utc)
		
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
				abs((event_start - event_time).total_seconds()) < 3600 and
				SequenceMatcher(None, event_title, event_summary).ratio() > DEDUP_THRESHOLD
			):
				try:
					existing.delete()
					count += 1
				except Exception as e:
					logger.error(f"Error deleting duplicate event '{event_summary}': {str(e)}")
		
		return count

	async def sync(self, events):
		"""Sync events to the appropriate calendars."""
		for event in events:
			#Check if event is Event object or Calendar object
			if isinstance(event, Event):
				await self.sync_event(event)
			elif isinstance(event, ICSCalendar):
				await self.sync_ics(event)
			else:
				logger.warning(f"Unsupported event type: {type(event)}. Skipping sync for this item.")
				continue

	async def sync_ics(self, ics_object) :
		"""Sync Calender ics object data to the calendars."""
		#Check which calendar to sync to
		event1 = None
		for event in ics_object.events:
			#logger.info(f"Syncing event {dir(event)} from ics object.")
			event1 = event
			break  # Only take the first event for now

		logger.info(f"Syncing event {event1.name} from ics object.")
		
		title = event1.name
		start_time = event1.begin.astimezone(timezone.utc)
		end_time = event1.end.astimezone(timezone.utc)

		if event1.status.upper() == 'CONFIRMED':
			calendar = self.confirmed_calendar
			calendar2 = self.possible_calendar
		else:
			calendar = self.possible_calendar
			calendar2 = self.confirmed_calendar

		#Check if event already exists in calendar
		existing_events = calendar.search(
			start=start_time - timedelta(days=1),
			end=end_time + timedelta(days=1),
			event=True,
			expand=True
		)

		existing_events2 = calendar2.search(
			start=start_time - timedelta(days=1),
			end=end_time + timedelta(days=1),
			event=True,
			expand=True
		)

		logger.info(f"Found {len(existing_events)} existing events in {calendar.name} for '{title}'")
		

		#Remove all events that match the event from calendar2
		duplicate_events = self._duplicate_events_ics(event1, existing_events2)
		if len(duplicate_events) > 0:
			logger.info(f"Removing Event '{title}' from the wrong calendar {calendar2.name}.")
			for event in duplicate_events:
				try:
					event.delete()
					logger.info(f"Removed duplicate event '{title}' from {calendar2.name}.")
				except Exception as e:
					logger.error(f"Error removing duplicate event '{title}' from {calendar2.name}: {str(e)}")

		# Check to see if the event is already in the correct calendar
		duplicate_events = self._duplicate_events_ics(event1, existing_events)
		if len(duplicate_events) == 1:
			logger.info(f"Event '{title}' already exists in {calendar.name}.")

			#Do a check to see if any of the event details have changed
			if self._event_properties_changed(event1, duplicate_events[0]):
				logger.info(f"Event '{title}' has changed. Updating in {calendar.name}.")
				#Remove the old event
				self._remove_duplicate_events(event1, calendar)
			else:
				logger.info(f"Event '{title}' has not changed. No action needed in {calendar.name}.")
				return
		elif len(duplicate_events) > 1:
			logger.warning(f"Multiple duplicate events found for '{title}' in {calendar.name}. This should not happen. Removing all duplicates.")
			#Remove all duplicates
			for event in duplicate_events:
				try:
					event.delete()
					logger.info(f"Removed duplicate event '{title}' from {calendar.name}.")
				except Exception as e:
					logger.error(f"Error removing duplicate event '{title}' from {calendar.name}: {str(e)}")

			#Add the event again
			try:
				calendar.save_event(ics_object.__str__())
				logger.info(f"Added event '{title}' to {calendar.name} after removing duplicates.")
			except Exception as e:
				logger.error(f"Error adding event '{title}' to {calendar.name}: {str(e)}")
		else:
			logger.info(f"Event '{title}' does not exist in {calendar.name}. Adding it.")
			# Add the event to the calendar
			try:
				#logger.info(f"ics_object: {ics_object} {dir(ics_object)}")
				calendar.save_event(ics_object.__str__())
				logger.info(f"Added event '{title}' to {calendar.name}")
			except Exception as e:
				logger.error(f"Error adding event '{title}' to {calendar.name}: {str(e)}")
				logger.error(traceback.format_exc())
		

	async def sync_event(self, event_object: Event):
		"""Sync a single Event object to the appropriate calendar."""
		#Check which calendar to sync to
		if event_object.is_confirmed:
			calendar = self.confirmed_calendar
			calendar2 = self.possible_calendar
		else:
			calendar = self.possible_calendar
			calendar2 = self.confirmed_calendar

		#Check if event already exists in calendar
		existing_events = calendar.search(
			start=event_object.start_time - timedelta(days=1),
			end=event_object.start_time + timedelta(days=1),
			event=True,
			expand=True
		)

		existing_events2 = calendar2.search(
			start=event_object.start_time - timedelta(days=1),
			end=event_object.start_time + timedelta(days=1),
			event=True,
			expand=True
		)

		#Remove all events that match the event from calendar2
		duplicate_events = self._duplicate_events(event_object, existing_events2)
		if len(duplicate_events) > 0:
			logger.info(f"Removing Event '{event_object.title}' from the wrong calendar {calendar2.name}.")
			for event in duplicate_events:
				try:
					event.delete()
					logger.info(f"Removed duplicate event '{event_object.title}' from {calendar2.name}.")
				except Exception as e:
					logger.error(f"Error removing duplicate event '{event_object.title}' from {calendar2.name}: {str(e)}")

		# Check to see if the event is already in the correct calendar
		duplicate_events = self._duplicate_events(event_object, existing_events)
		if len(duplicate_events) == 1:
			logger.info(f"Event '{event_object.title}' already exists in {calendar.name}.")

			#Do a check to see if any of the event details have changed
			if self._event_properties_changed(event_object, duplicate_events[0]):
				logger.info(f"Event '{event_object.title}' has changed. Updating in {calendar.name}.")
				#Remove the old event
				self._remove_duplicate_events(event_object, calendar)
			else:
				logger.info(f"Event '{event_object.title}' has not changed. No action needed in {calendar.name}.")
				return
		elif len(duplicate_events) > 1:
			logger.warning(f"Multiple duplicate events found for '{event_object.title}' in {calendar.name}. This should not happen. Removing all duplicates.")
			#Remove all duplicates
			for event in duplicate_events:
				try:
					event.delete()
					logger.info(f"Removed duplicate event '{event_object.title}' from {calendar.name}.")
				except Exception as e:
					logger.error(f"Error removing duplicate event '{event_object.title}' from {calendar.name}: {str(e)}")

			#Add the event again
			try:
				calendar.save_event(event_object)
				logger.info(f"Added event '{event_object.title}' to {calendar.name} after removing duplicates.")
			except Exception as e:
				logger.error(f"Error adding event '{event_object.title}' to {calendar.name}: {str(e)}")
		else:
			logger.info(f"Event '{event_object.title}' does not exist in {calendar.name}. Adding it.")
			# Add the event to the calendar
			try:
				calendar.save_event(event_object)
				logger.info(f"Added event '{event_object.title}' to {calendar.name}")
			except Exception as e:
				logger.error(f"Error adding event '{event_object.title}' to {calendar.name}: {str(e)}")
				logger.error(traceback.format_exc())