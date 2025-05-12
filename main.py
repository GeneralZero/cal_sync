import asyncio, sys, os
import logging
from datetime import datetime
from typing import List

from config import ENABLED_SOURCES, MAX_FUTURE_DAYS
from calendar_sync import CalendarSync
from event_source import Event, EventSource
from sources.meetup import MeetupEventSource
from sources.partiful import PartifulEventSource
from sources.eventbrite import EventbriteEventSource
from sources.nycsystems import NYCSystemsEventSource

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EventAggregator:
    def __init__(self):
        self.sources: List[EventSource] = []
        self.calendar_sync = CalendarSync()
        
        # Initialize enabled sources
        if ENABLED_SOURCES.get('meetup'):
            self.sources.append(MeetupEventSource())
        if ENABLED_SOURCES.get('partiful'):
            self.sources.append(PartifulEventSource())
        if ENABLED_SOURCES.get('eventbrite'):
            self.sources.append(EventbriteEventSource())
        if ENABLED_SOURCES.get('nycsystems'):
            self.sources.append(NYCSystemsEventSource())

    async def fetch_all_events(self) -> List[Event]:
        """Fetch events from all enabled sources."""
        all_events = []
        
        for source in self.sources:
            try:
                logger.info(f"Fetching events from {source.name()}")
                events = await source.fetch_events(days_ahead=MAX_FUTURE_DAYS)
                all_events.extend(events)
                logger.info(f"Found {len(events)} events from {source.name()}")
            except Exception as e:
                logger.error(f"Error fetching events from {source.name()}: {str(e)}")
        
        return all_events

    async def sync(self):
        """Main sync process."""
        try:
            # Fetch all events
            events = await self.fetch_all_events()
            logger.info(f"Found total of {len(events)} events")
            
            # Sync to calendar
            await self.calendar_sync.sync_events(events)
            logger.info("Synced events to calendar")
            
            logger.info("Sync completed successfully")
            
        except Exception as e:
            logger.error(f"Error during sync: {str(e)}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)

async def main():
    aggregator = EventAggregator()
    await aggregator.sync()

if __name__ == "__main__":
    asyncio.run(main()) 