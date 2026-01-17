import caldav
import os
import uuid
from datetime import datetime, timedelta
from loguru import logger

class CalDAVSyncManager:
    def __init__(self, url, username, password):
        self.url = url
        self.username = username
        self.password = password
        self.client = None

    def connect(self):
        """Establish connection to CalDAV server."""
        try:
            self.client = caldav.DAVClient(
                url=self.url,
                username=self.username,
                password=self.password
            )
            self.client.principal() # Verify credentials
            return True
        except Exception as e:
            logger.error(f"CalDAV connection failed: {e}")
            return False

    def sync_event(self, target_cal_name, event_date_str, summary, description):
        """
        Sync a single event to the target calendar.
        Handles duplicates and basic updates.
        """
        if not self.client:
            if not self.connect():
                return False

        try:
            # 1. Find Calendar
            target_calendar = self._find_calendar(target_cal_name)
            if not target_calendar:
                logger.error(f"Calendar '{target_cal_name}' not found.")
                return False

            # 2. Check for Duplicates
            dt_start = datetime.strptime(event_date_str, "%Y-%m-%d")
            
            duplicate_event = self._find_duplicate_event(target_calendar, dt_start, summary)
            
            if duplicate_event:
                logger.debug(f"Skipping duplicate event: {event_date_str} - {summary}")
                # TODO: Implement update/merge logic here in the future
                # e.g., if new summary is more detailed, update duplicate_event.
                return True
            
            # 3. Create New Event
            return self._create_event(target_calendar, dt_start, summary, description)

        except Exception as e:
            logger.error(f"Failed to sync event {event_date_str}: {e}")
            return False

    def _find_calendar(self, name):
        """Find calendar by name or display name."""
        try:
            principal = self.client.principal()
            calendars = principal.calendars()
            
            for cal in calendars:
                try:
                    props = cal.get_properties([caldav.dav.DisplayName()])
                    display_name = props.get(caldav.dav.DisplayName(), "").strip('"')
                    if display_name == name or cal.name == name:
                        return cal
                except:
                    if cal.name == name:
                        return cal
        except Exception as e:
            logger.error(f"Error searching calendars: {e}")
        return None

    def _find_duplicate_event(self, calendar, dt_start, summary):
        """Check if a similar event exists on the given day."""
        try:
            # Search range: the specific day
            search_dt = dt_start.date()
            existing = calendar.date_search(start=search_dt, end=search_dt)
            
            for ev in existing:
                # Check summary match
                if hasattr(ev, 'vobject_instance') and ev.vobject_instance:
                     if summary in ev.vobject_instance.vevent.summary.value:
                         return ev
                elif summary in ev.data:
                     return ev
        except Exception as e:
            logger.warning(f"CalDAV search failed (assuming no duplicate): {e}")
        return None

    def _create_event(self, calendar, dt_start, summary, description):
        """Create a new all-day event using raw iCalendar format."""
        try:
            dt_end = dt_start + timedelta(days=1)
            dt_start_str = dt_start.strftime("%Y%m%d")
            dt_end_str = dt_end.strftime("%Y%m%d")
            
            uid = str(uuid.uuid4())
            
            vcal_lines = [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Print-ETL-D//NONSGML v1.0//EN",
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}",
                f"DTSTART;VALUE=DATE:{dt_start_str}",
                f"DTEND;VALUE=DATE:{dt_end_str}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                "END:VEVENT",
                "END:VCALENDAR"
            ]
            vcal = "\r\n".join(vcal_lines) + "\r\n"
            
            calendar.add_event(vcal)
            logger.info(f"Added event to {calendar.name}: {dt_start_str} - {summary}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating event: {e}")
            return False
