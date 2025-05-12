# Calendar Event Aggregator

This project aggregates events from various sources (Partiful, Meetup.com, Eventbrite, etc.) and syncs them to CalDAV calendars. Events can be added to either a "Confirmed Events" calendar or a "Possible Events" calendar based on their status.

## Features

- Fetches events from multiple sources:
  - Partiful (using Firebase authentication)
  - Meetup.com
  - Eventbrite
  - NYC Systems
- Syncs events to CalDAV calendars
- Separates events into "Confirmed" and "Possible" calendars
- Automatic deduplication of events
- Configurable event sources and sync behavior

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Copy `sample.env` to `.env` and fill in your credentials:
   ```bash
   cp sample.env .env
   ```

3. Run the sync:
   ```bash
   python main.py
   ```

## Configuration

### Environment Variables (.env file)
- CalDAV Configuration:
  ```
  CALDAV_URL=your_caldav_server_url
  CALDAV_USERNAME=your_username
  CALDAV_PASSWORD=your_password
  CONFIRMED_CALENDAR_NAME=your_confirmed_calendar_name
  POSSIBLE_CALENDAR_NAME=your_possible_calendar_name
  ```
- Partiful Configuration:
  ```
  PARTIFUL_REFRESH_TOKEN=your_firebase_refresh_token
  PARTIFUL_API_KEY=your_firebase_api_key
  ```

### Obtaining Partiful Credentials

You can find these values in your browser's local storage:
1. In Developer Tools, go to the Storage tab
2. Find Indexed DB -> partiful.com -> firebaseLocalStorageDb -> firebaseLocalStorage
3. The api token should be at. fireabase:* -> value -> apiKey
4. The refresh token is located at.  fireabase:* -> value -> stsTokenManager -> refreshToken

Note: These credentials are sensitive and should be kept secure. Never share them or commit them to version control.

### Obtaining Meetup and Eventbrite IDs

#### Meetup Groups
For Meetup groups, you need the group's URL name. For example:
- URL: `https://www.meetup.com/rust-nyc/`
- Group ID: `rust-nyc`

To find a group's URL name:
1. Go to the group's Meetup page
2. The URL name is the last part of the URL after `meetup.com/`
3. Add it to `MEETUP_GROUPS` in `config.py`

#### Eventbrite Organizers
For Eventbrite organizers, you need the organizer ID. For example:
- URL: `https://www.eventbrite.com/o/project-nutype-29377900795`
- Organizer ID: `29377900795`

To find an organizer's ID:
1. Go to the organizer's Eventbrite page
2. The ID is the last number in the URL after `o/`
3. Add it to `EVENTBRITE_ORGANIZER_IDS` in `config.py`

### Event Sources (config.py)
- Enable/disable event sources:
  ```python
  ENABLED_SOURCES = {
      'meetup': True,
      'partiful': True,
      'eventbrite': True,
      'nycsystems': True,
  }
  ```
- Configure Eventbrite organizers:
  ```python
  EVENTBRITE_ORGANIZER_IDS = [
      "29377900795",  # Project Nutype
      "86136754923",  # Lectures on Tap
      # Add more organizer IDs here
  ]
  ```
- Configure Meetup groups:
  ```python
  MEETUP_GROUPS = [
      "fat-cat-fab-lab",
      "new-york-c-c-meetup-group",
      "papers-we-love",
      "nycultimate",
      "rust-nyc",
      "hackmanhattan"
      # Add more groups here
  ]
  ```

### Sync Settings (config.py)
- `MAX_FUTURE_DAYS`: How far into the future to fetch events (default: 90)
- `DEDUP_THRESHOLD`: Similarity threshold for deduplication (default: 0.85)

## Adding New Event Sources

To add a new event source:

1. Create a new file in the `sources` directory
2. Implement the `EventSource` interface
3. Add the source to `config.py` and `ENABLED_SOURCES`

## License

MIT License 