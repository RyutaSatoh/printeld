import unittest
from unittest.mock import MagicMock, patch
import asyncio
from pathlib import Path
from print_etl_d.dispatcher import Dispatcher
from print_etl_d.config import ActionConfig
import os

class TestCalDAVSync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dispatcher = Dispatcher()
        self.action = ActionConfig(
            type="add_caldav_event",
            calendar_url="http://fake-caldav.com",
            username_env="TEST_USER",
            password_env="TEST_PASS",
            calendar_map={"test_category": "Test Calendar"}
        )
        os.environ["TEST_USER"] = "user"
        os.environ["TEST_PASS"] = "pass"

    @patch("caldav.DAVClient")
    async def test_add_caldav_event_success(self, mock_client_cls):
        # Setup mocks
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        
        mock_principal = MagicMock()
        mock_client.principal.return_value = mock_principal
        
        mock_calendar = MagicMock()
        mock_calendar.name = "Test Calendar"
        mock_calendar.url = "http://fake-caldav.com/cal1"
        mock_calendar.get_properties.return_value = {
            # DisplayName property
            "{DAV:}displayname": "Test Calendar"
        }
        mock_calendar.date_search.return_value = [] # No duplicates
        
        mock_principal.calendars.return_value = [mock_calendar]
        
        data = {
            "category_folder": "test_category",
            "school_details": {
                "schedule_list": [
                    {
                        "date": "2026-01-20",
                        "special_items": ["item1"],
                        "irregular_schedule": "event1"
                    }
                ]
            }
        }
        
        # Run sync
        await self.dispatcher.dispatch([self.action], data, Path("test.pdf"))
        
        # Verify
        mock_calendar.add_event.assert_called_once()
        vcal_arg = mock_calendar.add_event.call_args[0][0]
        self.assertIn("SUMMARY:item1 / event1", vcal_arg)
        self.assertIn("DTSTART;VALUE=DATE:20260120", vcal_arg)

    @patch("caldav.DAVClient")
    async def test_add_caldav_event_duplicate_skip(self, mock_client_cls):
        # Setup mocks
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_principal = MagicMock()
        mock_client.principal.return_value = mock_principal
        
        mock_calendar = MagicMock()
        mock_calendar.name = "Test Calendar"
        mock_calendar.get_properties.return_value = {"{DAV:}displayname": "Test Calendar"}
        
        # Mock an existing event with same summary
        mock_existing_event = MagicMock()
        mock_existing_event.data = "SUMMARY:item1 / event1"
        mock_calendar.date_search.return_value = [mock_existing_event]
        
        mock_principal.calendars.return_value = [mock_calendar]
        
        data = {
            "category_folder": "test_category",
            "school_details": {
                "schedule_list": [
                    {
                        "date": "2026-01-20",
                        "special_items": ["item1"],
                        "irregular_schedule": "event1"
                    }
                ]
            }
        }
        
        # Run sync
        await self.dispatcher.dispatch([self.action], data, Path("test.pdf"))
        
        # Verify save_event was NOT called
        mock_calendar.add_event.assert_not_called()

if __name__ == "__main__":
    unittest.main()
