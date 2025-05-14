import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# CalDAV Configuration
CALDAV_URL = os.getenv('CALDAV_URL')
CALDAV_USERNAME = os.getenv('CALDAV_USERNAME')
CALDAV_PASSWORD = os.getenv('CALDAV_PASSWORD')

# Calendar Names
CONFIRMED_CALENDAR = os.getenv('CONFIRMED_CALENDAR_NAME', 'Confirmed Events')
POSSIBLE_CALENDAR = os.getenv('POSSIBLE_CALENDAR_NAME', 'Possible Events')

# Event Source Configuration
MEETUP_API_KEY = os.getenv('MEETUP_API_KEY')

# Event Sources Settings
ENABLED_SOURCES = {
	'meetup': True,
	'partiful': True,
	'eventbrite': True,
	'nycsystems': True,
}

# Eventbrite Configuration
EVENTBRITE_ORGANIZER_IDS = [
	"29377900795",  # Project Nutype
	"86136754923",  # Lectures on Tap
	# Add more organizer IDs here
]

# Meetup Configuration
MEETUP_GROUPS = [
	"fat-cat-fab-lab",
	"new-york-c-c-meetup-group",
	"papers-we-love",
	"nycultimate",
	"rust-nyc",
	"hackmanhattan"
	# Add more groups here
]

# Sync Settings
MAX_FUTURE_DAYS = 90     # How far into the future to fetch events
DEDUP_THRESHOLD = 0.85   # Similarity threshold for deduplication
