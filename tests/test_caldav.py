import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from print_etl_d.caldav_sync import CalDAVSyncManager

class TestCalDAVSyncManager(unittest.TestCase):
    @patch("caldav.DAVClient")
    def test_sync_event_new(self, mock_client_cls):
        # Setup Mocks
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_calendar = MagicMock()
        mock_calendar.name = "Test Calendar"
        
        # Mock finding calendar
        mock_principal = MagicMock()
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        
        # Mock duplicates check (none found)
        mock_calendar.date_search.return_value = []
        
        manager = CalDAVSyncManager("http://url", "user", "pass")
        
        # Run
        result = manager.sync_event("Test Calendar", "2026-01-20", "Summary", "Desc")
        
        # Verify
        self.assertTrue(result)
        mock_calendar.add_event.assert_called_once()
        vcal_arg = mock_calendar.add_event.call_args[0][0]
        self.assertIn("SUMMARY:Summary", vcal_arg)
        self.assertIn("DESCRIPTION:Desc", vcal_arg)

    @patch("caldav.DAVClient")
    def test_sync_event_duplicate(self, mock_client_cls):
        # Setup Mocks
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_calendar = MagicMock()
        mock_calendar.name = "Test Calendar"
        
        mock_principal = MagicMock()
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        
        # Mock existing event
        mock_event = MagicMock()
        # Mocking data attribute correctly
        mock_event.data = "SUMMARY:Summary" 
        # Ensure vobject_instance doesn't interfere if checked
        mock_event.vobject_instance = None
        
        mock_calendar.date_search.return_value = [mock_event]
        
        manager = CalDAVSyncManager("http://url", "user", "pass")
        
        # Run
        result = manager.sync_event("Test Calendar", "2026-01-20", "Summary", "Desc")
        
        # Verify
        self.assertTrue(result)
        mock_calendar.add_event.assert_not_called() # Should skipped

if __name__ == "__main__":
    unittest.main()