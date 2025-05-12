import aiohttp
from datetime import datetime, timezone, timedelta
from typing import List
import logging
from pprint import pprint
from event_source import EventSource, Event
from config import MEETUP_GROUPS

logger = logging.getLogger(__name__)

class MeetupEventSource(EventSource):
    GQL_URL = "https://www.meetup.com/gql2"
    QUERY_HASH = "e1a588d73cb23d2cff73d5f6afa677d26e1e905835d084afb93ae5c456cc4812"

    def name(self) -> str:
        return "meetup"

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

    async def fetch_events(self, days_ahead: int = 90) -> List[Event]:
        """Fetch events from Meetup.com GraphQL API."""
        events = []
        now = datetime.now(timezone.utc)
        max_date = now + timedelta(days=days_ahead)
        
        async with aiohttp.ClientSession() as session:
            for group in MEETUP_GROUPS:
                try:
                    # Prepare the GraphQL query
                    query_data = {
                        "operationName": "getUpcomingGroupEvents",
                        "variables": {
                            "urlname": group,
                            "afterDateTime": now.isoformat(),
                            "first": 50  # Limit to 50 events per group
                        },
                        "extensions": {
                            "persistedQuery": {
                                "version": 1,
                                "sha256Hash": self.QUERY_HASH
                            }
                        }
                    }

                    headers = {
                        "Content-Type": "application/json",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    }

                    async with session.post(self.GQL_URL, json=query_data, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            # Extract events from the GraphQL response
                            # Note: We'll need to adjust the path to events based on the actual response structure
                            group_events = data.get("data", {}).get("groupByUrlname", {}).get("events", []).get("edges", [])
                            
                            for event_data in group_events:
                                try:
                                    node = event_data["node"]
                                    start_time = self._parse_datetime(node["dateTime"].replace("Z", "+00:00"))
                                    
                                    # If event has duration, use it; otherwise default to 2 hours
                                    duration_minutes = node.get("duration", 120)
                                    end_time = start_time + timedelta(minutes=duration_minutes)

                                    # Get venue information
                                    venue = node.get("venue", {})
                                    location = None
                                    if venue:
                                        address_parts = []
                                        if venue.get("name"):
                                            address_parts.append(venue["name"])
                                        if venue.get("address"):
                                            address_parts.append(venue["address"])
                                        if venue.get("city"):
                                            address_parts.append(venue["city"])
                                        if venue.get("state"):
                                            address_parts.append(venue["state"])
                                        location = ", ".join(filter(None, address_parts))

                                    event = Event(
                                        title=node["title"],
                                        start_time=start_time,
                                        end_time=end_time,
                                        description=node.get("description", ""),
                                        location=location or "",
                                        url=node.get("eventUrl"),
                                        is_confirmed=False,  # Meetup events are considered un_confirmed
                                        source=self.name(),
                                        source_id=str(node.get("id"))
                                    )
                                    events.append(event)
                                    #logger.info(f"Found Meetup event: {event.title} for group {group}")
                                    
                                except (KeyError, ValueError) as e:
                                    logger.error(f"Error parsing Meetup event for group {group}: {str(e)}")
                                    continue
                        else:
                            response_text = await response.text()
                            logger.error(f"Meetup GraphQL request failed for group {group} with status {response.status}: {response_text}")

                except Exception as e:
                    logger.error(f"Error fetching Meetup events for group {group}: {str(e)}")

        return events 