from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

@dataclass
class Event:
	title: str
	start_time: datetime
	end_time: datetime
	description: Optional[str] = None
	location: Optional[str] = None
	url: Optional[str] = None
	is_confirmed: bool = False
	source: Optional[str] = None
	source_id: Optional[str] = None

class EventSource(ABC):
	"""Base class for all event sources."""
	
	@abstractmethod
	async def fetch_events(self, days_ahead: int = 90) -> List[Event]:
		"""
		Fetch events from the source.
		
		Args:
			days_ahead: How many days into the future to fetch events for
			
		Returns:
			List of Event objects
		"""
		pass
	
	@abstractmethod
	def name(self) -> str:
		"""Return the name of this event source."""
		pass 