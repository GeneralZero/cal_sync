import aiohttp
from datetime import datetime, timezone, timedelta
from typing import List
import logging
import json
import os
import uuid
import base64
from ics import Calendar
from dotenv import load_dotenv, set_key
from pathlib import Path

from event_source import EventSource, Event

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class PartifulEventSource(EventSource):
	API_URL = "https://api.partiful.com/getMyRsvps"
	FIREBASE_TOKEN_URL = "https://securetoken.googleapis.com/v1/token"
	FIREBASE_API_KEY = os.getenv('PARTIFUL_API_KEY')
	FIREBASE_PROJECT_ID = "939741910890"
	FIREBASE_APP_ID = "1:939741910890:web:5cca435c4b26209b8a7713"
	
	def __init__(self, ics_files: bool = False):
		self.refresh_token = os.getenv('PARTIFUL_REFRESH_TOKEN')
		self.access_token = None
		self.user_id = None
		self.ics_files = ics_files
		if not self.refresh_token:
			logger.error("PARTIFUL_REFRESH_TOKEN not found in environment variables")
		if not self.FIREBASE_API_KEY:
			logger.error("PARTIFUL_API_KEY not found in environment variables")

	def name(self) -> str:
		return "partiful"

	def _generate_idempotency_key(self) -> str:
		"""Generate a unique idempotency key."""
		return str(uuid.uuid4().int % 9000000000000000000 + 1000000000000000000)

	async def _refresh_token(self, session: aiohttp.ClientSession) -> bool:
		"""Refresh the access token using Firebase Authentication."""
		try:
			headers = {
				"Accept-Language": "en-US",
				"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.127 Safari/537.36",
				"Content-Type": "application/x-www-form-urlencoded",
				"X-Firebase-Gmpid": self.FIREBASE_APP_ID,
				"X-Client-Version": "Chrome/JsCore/11.2.0/FirebaseCore-web",
				"Origin": "https://partiful.com",
				"Referer": "https://partiful.com/",
				"Accept": "*/*"
			}

			data = {
				"grant_type": "refresh_token",
				"refresh_token": self.refresh_token
			}

			url = f"{self.FIREBASE_TOKEN_URL}?key={self.FIREBASE_API_KEY}"
			
			async with session.post(url, headers=headers, data=data) as response:
				if response.status == 200:
					response_data = await response.json()
					self.access_token = response_data["access_token"]
					self.id_token = response_data["id_token"]
					self.user_id = response_data["user_id"]
					logger.info("Successfully refreshed Partiful access token")
					return True
				else:
					response_text = await response.text()
					logger.error(f"Token refresh failed with status {response.status}: {response_text}")
					return False
		except Exception as e:
			logger.error(f"Error refreshing token: {str(e)}")
			return False

	def _parse_datetime(self, date_str: str) -> datetime:
		"""Parse datetime string and ensure it's timezone-aware."""
		try:
			# Remove 'Z' and add UTC timezone
			if date_str.endswith('Z'):
				date_str = date_str[:-1] + '+00:00'
			# Parse the string to datetime
			dt = datetime.fromisoformat(date_str)
			# If the datetime is naive, make it UTC
			if dt.tzinfo is None:
				dt = dt.replace(tzinfo=timezone.utc)
			return dt
		except Exception as e:
			logger.error(f"Error parsing datetime {date_str}: {str(e)}")
			raise ValueError(f"Invalid datetime format: {date_str}")

	async def fetch_events(self, days_ahead: int = 90):
		#Check if ics_files is enabled
		if self.ics_files:
			return await self.fetch_events_ics(days_ahead)
		else:
			return await self.fetch_events_old(days_ahead)
		
	async def fetch_events_ics(self, days_ahead: int = 90) -> List[Calendar]:
		"""Fetch events from Partiful API and download ICS files."""
		if not self.refresh_token or not self.FIREBASE_API_KEY:
			logger.error("Cannot fetch Partiful events: Missing refresh token or API key")
			return []

		events = []
		
		async with aiohttp.ClientSession() as session:
			# First refresh the access token
			if not await self._refresh_token(session):
				return []
			
			events = []

			try:
				headers = {
					"Authorization": f"Bearer {self.id_token}",
					"Content-Type": "application/json",
					"Accept": "*/*",
					"Accept-Language": "en-US,en;q=0.5",
					"Origin": "https://partiful.com",
					"Referer": "https://partiful.com/",
					"Idempotency-Key": f'"{self._generate_idempotency_key()}"',
					"DNT": "1",
					"Sec-GPC": "1",
					"Sec-Fetch-Dest": "empty",
					"Sec-Fetch-Mode": "cors",
					"Sec-Fetch-Site": "same-site",
					"Cache-Control": "no-cache",
					"Pragma": "no-cache"
				}

				data = {
					"data": {
						"params": {},
						"userId": self.user_id
					}
				}

				async with session.post(self.API_URL, headers=headers, json=data) as response:
					if response.status == 200:
						data = await response.json()
						now = datetime.now(timezone.utc)
						
						for event_data in data.get("result", {}).get("data", {}).get("events", []):
							# Check to see if the event has passed
							if "startDate" in event_data:
								try:
									# Parse start date with timezone handling
									start_time = self._parse_datetime(event_data["startDate"])
									if start_time < now:
										#logger.info(f"Skipping past event {event_data['id']} with start time {start_time}")
										continue
								except ValueError as e:
									logger.error(f"Error parsing start date for event {event_data['id']}: {str(e)}")
									continue
							else:
								logger.warning(f"Event {event_data['id']} does not have a start date, skipping")
								continue

							#logger.info(f"Processing event {event_data}")
							if event_data.get("calendarFile"):
								logger.info(f"Downloading calendar ICS file for event {event_data['id']}")
								try:
									ics_url = event_data["calendarFile"]
									async with session.get(ics_url) as ics_response:
										if ics_response.status == 200:
											ics_content = await ics_response.text()
											# Parse the ICS content
											calendar = Calendar(ics_content)
											events.append(calendar)

								except Exception as e:
									logger.error(f"Error downloading ICS file for event {event_data['id']}: {str(e)}")
									continue
							else:
								logger.warning(f"No calendar URL found for event {event_data['id']}, skipping ICS download")
								continue
				
					elif response.status == 401:
						# Try to refresh token and retry the request once
						logger.info("Token expired, attempting to refresh...")
						if await self._refresh_token(session):
							# Retry the request with new token
							headers["Authorization"] = f"Bearer {self.id_token}"
							async with session.post(self.API_URL, headers=headers, json=data) as retry_response:
								if retry_response.status == 200:
									retry_data = await retry_response.json()
									# Process events (same code as above)
									for event_data in retry_data.get("result", {}).get("data", {}).get("events", []):
										if event_data.get("calendarUrl"):
											logger.info(f"Downloading calendar ICS file for event {event_data['id']}")
											try:
												ics_url = event_data["calendarUrl"]
												async with session.get(ics_url) as ics_response:
													if ics_response.status == 200:
														ics_content = await ics_response.text()
														calendar = Calendar(ics_content)
														events.append(calendar)
											except Exception as e:
												logger.error(f"Error downloading ICS file for event {event_data['id']}: {str(e)}")
												continue
								else:
									logger.error("Failed to fetch events even after token refresh")
						else:
							logger.error("Failed to refresh token")
					else:
						response_text = await response.text()
						logger.error(f"Partiful API request failed with status {response.status} and data {response_text}")
			except Exception as e:
				logger.error(f"Error fetching Partiful events: {str(e)}")
		return events
	
	
	async def fetch_events_old(self, days_ahead: int = 90) -> List[Event]:
		"""Fetch events from Partiful API."""
		if not self.refresh_token or not self.FIREBASE_API_KEY:
			logger.error("Cannot fetch Partiful events: Missing refresh token or API key")
			return []

		events = []
		
		async with aiohttp.ClientSession() as session:
			# First refresh the access token
			if not await self._refresh_token(session):
				return []

			try:
				headers = {
					"Authorization": f"Bearer {self.id_token}",
					"Content-Type": "application/json",
					"Accept": "*/*",
					"Accept-Language": "en-US,en;q=0.5",
					"Origin": "https://partiful.com",
					"Referer": "https://partiful.com/",
					"Idempotency-Key": f'"{self._generate_idempotency_key()}"',
					"DNT": "1",
					"Sec-GPC": "1",
					"Sec-Fetch-Dest": "empty",
					"Sec-Fetch-Mode": "cors",
					"Sec-Fetch-Site": "same-site",
					"Cache-Control": "no-cache",
					"Pragma": "no-cache"
				}

				# Required JSON data structure
				data = {
					"data": {
						"params": {},
						"userId": self.user_id
					}
				}

				async with session.post(self.API_URL, headers=headers, json=data) as response:
					if response.status == 200:
						data = await response.json()
						now = datetime.now(timezone.utc)
						
						# Process each event from the API response
						for event_data in data.get("result", {}).get("data", {}).get("events", []):
							try:
								# Parse start date with timezone handling
								start_time = self._parse_datetime(event_data["startDate"])
								
								# Skip events that have already happened
								if start_time < now:
									continue
								
								# Handle end date (default to 3 hours if not specified)
								if event_data.get("endDate"):
									end_time = self._parse_datetime(event_data["endDate"])
								else:
									end_time = start_time + timedelta(hours=3)
								
								# Create Event object
								event = Event(
									title=event_data["title"],
									start_time=start_time,
									end_time=end_time,
									description=event_data.get("description", ""),
									location=event_data.get("location", ""),
									url=f"https://partiful.com/e/{event_data['id']}",
									is_confirmed=event_data.get("guest", {}).get("status") == "GOING",
									source=self.name(),
									source_id=event_data["id"]
								)
								events.append(event)
								
							except (KeyError, ValueError) as e:
								logger.error(f"Error parsing Partiful event: {str(e)}")
								continue
					elif response.status == 401:
						# Try to refresh token and retry the request once
						logger.info("Token expired, attempting to refresh...")
						if await self._refresh_token(session):
							# Retry the request with new token
							headers["Authorization"] = f"Bearer {self.id_token}"
							async with session.post(self.API_URL, headers=headers, json=data) as retry_response:
								if retry_response.status == 200:
									retry_data = await retry_response.json()
									# Process events (same code as above)
									for event_data in retry_data.get("result", {}).get("data", {}).get("events", []):
										try:
											start_time = self._parse_datetime(event_data["startDate"])
											if start_time < now:
												continue
											if event_data.get("endDate"):
												end_time = self._parse_datetime(event_data["endDate"])
											else:
												end_time = start_time + timedelta(hours=3)
											event = Event(
												title=event_data["title"],
												start_time=start_time,
												end_time=end_time,
												description=event_data.get("description", ""),
												location=event_data.get("location", ""),
												url=f"https://partiful.com/e/{event_data['id']}",
												is_confirmed=event_data.get("guest", {}).get("status") == "GOING",
												source=self.name(),
												source_id=event_data["id"]
											)
											events.append(event)
										except (KeyError, ValueError) as e:
											logger.error(f"Error parsing Partiful event after token refresh: {str(e)}")
											continue
								else:
									logger.error("Failed to fetch events even after token refresh")
						else:
							logger.error("Failed to refresh token")
					else:
						response_text = await response.text()
						logger.error(f"Partiful API request failed with status {response.status} and data {response_text}")

			except Exception as e:
				logger.error(f"Error fetching Partiful events: {str(e)}")

		return events 