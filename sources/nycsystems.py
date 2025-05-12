import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from typing import List
import logging
import re
import zoneinfo

from event_source import EventSource, Event

logger = logging.getLogger(__name__)

class NYCSystemsEventSource(EventSource):
    BASE_URL = "https://nycsystems.xyz"
    DESCRIPTION = """NYC Systems is an independent tech talk series focused on systems programming. It is entirely community-run, not affiliated with any company.

Topics include:
• Compilers, parsers, virtual machines, IDEs, profiling
• Databases, storage, networking, distributed systems
• Large scale infrastructure, low latency, high availability services
• Formal methods, verification
• Browsers, kernel development, security

Previous talks available at: https://youtube.com/@NYCSystems"""

    LOCATION = "Trail of Bits Office, New York"
    START_HOUR = 18  # 6:30 PM
    START_MINUTE = 30
    DURATION_HOURS = 2
    
    def name(self) -> str:
        return "nycsystems"

    async def fetch_events(self, days_ahead: int = 90) -> List[Event]:
        """Fetch events from NYC Systems website."""
        events = []
        now = datetime.now(timezone.utc)
        
        async with aiohttp.ClientSession() as session:
            try:
                # Fetch the main page
                async with session.get(self.BASE_URL) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Find the schedule table
                        schedule_table = soup.find('table')
                        if not schedule_table:
                            logger.error("Could not find schedule table on NYC Systems page")
                            return events

                        # Process each row in the schedule
                        for row in schedule_table.find_all('tr')[1:]:  # Skip header row
                            try:
                                columns = row.find_all('td')
                                if len(columns) < 2:
                                    continue

                                # Extract date and speakers
                                date_cell = columns[0]
                                date_text = date_cell.text.strip()
                                speakers_text = columns[1].text.strip()
                                
                                # Parse the date (format: "Month DD")
                                try:
                                    # Get the year from the URL or default to next occurrence
                                    year = 2025  # Default to 2025 based on the website
                                    
                                    # Parse the month and day
                                    date_str = f"{date_text} {year}"
                                    naive_date = datetime.strptime(date_str, "%B %d %Y")
                                    
                                    # Create datetime in Eastern Time at 6:30 PM
                                    et_zone = zoneinfo.ZoneInfo("America/New_York")
                                    start_time = naive_date.replace(
                                        hour=self.START_HOUR,
                                        minute=self.START_MINUTE,
                                        tzinfo=et_zone
                                    )
                                    
                                    # Convert to UTC for storage
                                    start_time = start_time.astimezone(timezone.utc)
                                    
                                    # Skip if event is in the past or too far in the future
                                    if start_time < now or (start_time - now).days > days_ahead:
                                        continue

                                    # Set end time to 2 hours after start
                                    end_time = start_time + timedelta(hours=self.DURATION_HOURS)

                                    # Get event details link if available
                                    event_link = None
                                    link_elem = date_cell.find('a')
                                    if link_elem and link_elem.get('href'):
                                        event_link = f"{self.BASE_URL}{link_elem['href']}"

                                    # Create title based on speakers
                                    if speakers_text.lower() == 'tbd':
                                        title = f"NYC Systems Talk - {date_text}"
                                    else:
                                        title = f"NYC Systems Talk - {speakers_text}"

                                    event = Event(
                                        title=title,
                                        start_time=start_time,
                                        end_time=end_time,
                                        description=self.DESCRIPTION,
                                        location=self.LOCATION,
                                        url=event_link or self.BASE_URL,
                                        is_confirmed=speakers_text.lower() != 'tbd',
                                        source=self.name(),
                                        source_id=f"nycsystems_{start_time.strftime('%Y%m%d')}"
                                    )
                                    events.append(event)
                                    
                                except ValueError as e:
                                    logger.error(f"Error parsing date for NYC Systems event: {str(e)}")
                                    continue
                                
                            except Exception as e:
                                logger.error(f"Error processing NYC Systems event row: {str(e)}")
                                continue
                    else:
                        logger.error(f"NYC Systems website request failed with status {response.status}")

            except Exception as e:
                logger.error(f"Error fetching NYC Systems events: {str(e)}")

        return events 