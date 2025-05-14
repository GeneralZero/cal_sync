import aiohttp
from datetime import datetime, timezone, timedelta
from typing import List, Dict
import logging
import json
import re
import zoneinfo

from event_source import EventSource, Event
from config import EVENTBRITE_ORGANIZER_IDS

logger = logging.getLogger(__name__)

class EventbriteEventSource(EventSource):
	API_URL = "https://www.eventbrite.com/api/v3/destination/events/"
	
	def name(self) -> str:
		return "eventbrite"

	async def _get_event_ids_from_organizer(self, session: aiohttp.ClientSession, organizer_id: str) -> List[str]:
		"""Get event IDs from an organizer's page."""
		event_ids = []
		try:
			url = f"https://www.eventbrite.com/o/{organizer_id}"
			headers = {
				"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
			}
			
			async with session.get(url, headers=headers) as response:
				if response.status == 200:
					text = await response.text()
					# Find the SERVER_DATA JSON
					match = re.search(r'window\.__SERVER_DATA__\s*=\s*({.*?});', text, re.DOTALL)
					if match:
						data = json.loads(match.group(1))
						# Extract event IDs from the events list
						events = data.get("view_data", {}).get("events", {})
						future_events = events.get("future_events", [])
						event_ids.extend(str(event["id"]) for event in future_events)
				else:
					logger.error(f"Failed to fetch organizer page {organizer_id}: {response.status}")
		except Exception as e:
			logger.error(f"Error getting event IDs from organizer {organizer_id}: {str(e)}")
		
		return event_ids

	async def _get_events_details(self, session: aiohttp.ClientSession, event_ids: List[str]) -> List[Dict]:
		"""Get detailed event information from the API."""
		if not event_ids:
			return []
			
		try:
			params = {
				"event_ids": ",".join(event_ids),
				"expand": "event_sales_status,image,primary_venue,saves,series,ticket_availability,primary_organizer",
				"page_size": "50",
				"include_parent_events": "true"
			}
			
			headers = {
				"Accept-Language": "en-US",
				"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.127 Safari/537.36",
				"Accept": "*/*",
				"Referer": f"https://www.eventbrite.com/o/{EVENTBRITE_ORGANIZER_IDS[0]}",
				"Accept-Encoding": "gzip, deflate, br"
			}

			async with session.get(self.API_URL, params=params, headers=headers) as response:
				if response.status == 200:
					data = await response.json()
					return data.get("events", [])
				else:
					logger.error(f"Failed to fetch event details: {response.status}")
					response_text = await response.text()
					logger.error(f"Response: {response_text}")
		except Exception as e:
			logger.error(f"Error getting event details: {str(e)}")
		
		return []

	def _parse_datetime(self, date: str, time: str, timezone_str: str) -> datetime:
		"""Parse date and time strings into a timezone-aware datetime object."""
		try:
			# Combine date and time strings
			datetime_str = f"{date}T{time}"
			# Parse into datetime object
			dt = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M")
			# Attach timezone
			tz = zoneinfo.ZoneInfo(timezone_str)
			dt = dt.replace(tzinfo=tz)
			# Convert to UTC
			return dt.astimezone(timezone.utc)
		except Exception as e:
			logger.error(f"Error parsing datetime {date} {time} {timezone_str}: {str(e)}")
			raise ValueError(f"Invalid datetime format: {date} {time}")

	async def fetch_events(self, days_ahead: int = 360) -> List[Event]:
		"""Fetch events from Eventbrite API."""
		events = []
		now = datetime.now(timezone.utc)
		max_date = now + timedelta(days=days_ahead)
		
		async with aiohttp.ClientSession() as session:
			# First get all event IDs from organizers
			all_event_ids = []
			for organizer_id in EVENTBRITE_ORGANIZER_IDS:
				event_ids = await self._get_event_ids_from_organizer(session, organizer_id)
				all_event_ids.extend(event_ids)
			
			# Then get detailed event information
			event_details = await self._get_events_details(session, all_event_ids)

			#logger.info(f"event_details: {event_details}")
			
			# Process events
			for event_data in event_details:
				try:
					# Check if this is a recurring event series
					series = event_data.get("series", {})
					#logger.info(f"event_data: {event_data}")
					if series and series.get("next_dates"):
						# Process each date in the series
						for date_info in series["next_dates"]:
							try:
								# Parse start and end times (already in UTC)
								start_time = datetime.fromisoformat(date_info["start"].replace("Z", "+00:00"))
								end_time = datetime.fromisoformat(date_info["end"].replace("Z", "+00:00"))

								logger.info(f"Event data: {event_data.get('name')} {start_time} {end_time}")
								
								# Get venue information
								venue = event_data.get("primary_venue", {})
								location = None
								if venue:
									location = f"{venue.get('name', '')}, {venue.get('address', {}).get('localized_address_display', '')}"
									location = location.strip(", ")  # Remove extra commas and spaces

								# Create Event object for this occurrence
								event = Event(
									title=event_data["name"],
									start_time=start_time,
									end_time=end_time,
									description=event_data.get("summary", ""),
									location=location,
									url=event_data.get("url"),
									# Consider event confirmed if it's live/started and not cancelled
									is_confirmed=False,
									source=self.name(),
									source_id=str(date_info["id"])  # Use the specific occurrence ID
								)
								events.append(event)
								
							except (KeyError, ValueError) as e:
								logger.error(f"Error parsing recurring event date: {str(e)}")
								continue
					else:
						# Handle non-recurring events
						timezone_str = event_data.get("timezone", "America/New_York")
						start_time = self._parse_datetime(
							event_data["start_date"],
							event_data["start_time"],
							timezone_str
						)
						
						# Skip if outside our date range
						if start_time < now or start_time > max_date:
							continue
						
						end_time = self._parse_datetime(
							event_data["end_date"],
							event_data["end_time"],
							timezone_str
						)

						# Get venue information
						venue = event_data.get("primary_venue", {})
						location = None
						if venue:
							location = f"{venue.get('name', '')}, {venue.get('address', {}).get('localized_address_display', '')}"
							location = location.strip(", ")

						# Create Event object
						event = Event(
							title=event_data["name"],
							start_time=start_time,
							end_time=end_time,
							description=event_data.get("summary", ""),
							location=location,
							url=event_data.get("url"),
							is_confirmed=False,
							source=self.name(),
							source_id=str(event_data["id"])
						)
						events.append(event)
					
				except (KeyError, ValueError) as e:
					logger.error(f"Error parsing Eventbrite event: {str(e)}")
					continue

		return events 