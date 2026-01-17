import unittest
from unittest.mock import MagicMock, patch
import asyncio
import shutil
import tempfile
import json
import os
from pathlib import Path
from print_etl_d.dispatcher import Dispatcher
from print_etl_d.config import ActionConfig

class TestDispatcher(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.output_file = self.test_dir / "output.json"
        self.dispatcher = Dispatcher()
        os.environ["TEST_USER"] = "user"
        os.environ["TEST_PASS"] = "pass"

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir)

    async def test_save_json_append(self):
        action = ActionConfig(type="save_json", path=str(self.output_file))
        data1 = {"id": 1}
        data2 = {"id": 2}
        
        await self.dispatcher.dispatch([action], data1, Path("dummy.pdf"))
        
        with open(self.output_file, "r") as f:
            content = json.load(f)
            self.assertEqual(len(content), 1)
            
        await self.dispatcher.dispatch([action], data2, Path("dummy.pdf"))
        
        with open(self.output_file, "r") as f:
            content = json.load(f)
            self.assertEqual(len(content), 2)

    async def test_move_file_copy(self):
        source_file = self.test_dir / "source.pdf"
        source_file.write_text("fake pdf content")
        dest_dir = self.test_dir / "dest"
        
        action = ActionConfig(
            type="move_file",
            base_dir=str(dest_dir),
            path_template="{val}/{original_name}.pdf"
        )
        data = {"val": "folder1"}
        
        await self.dispatcher.dispatch([action], data, source_file)
        
        expected = dest_dir / "folder1" / "source.pdf"
        self.assertTrue(expected.exists())

    @patch("print_etl_d.dispatcher.CalDAVSyncManager")
    async def test_add_caldav_event_delegation(self, mock_manager_cls):
        # Mock Manager instance
        mock_manager = MagicMock()
        mock_manager_cls.return_value = mock_manager
        mock_manager.connect.return_value = True
        
        action = ActionConfig(
            type="add_caldav_event",
            calendar_url="http://fake",
            username_env="TEST_USER",
            password_env="TEST_PASS",
            calendar_map={"test": "TestCal"}
        )
        
        data = {
            "category_folder": "test",
            "school_details": {
                "schedule_list": [
                    {"date": "2026-01-20", "special_items": ["A"], "irregular_schedule": "B"}
                ]
            }
        }
        
        await self.dispatcher.dispatch([action], data, Path("doc.pdf"))
        
        # Verify Manager was instantiated and called
        mock_manager_cls.assert_called_with("http://fake", "user", "pass")
        mock_manager.sync_event.assert_called_once()
        args = mock_manager.sync_event.call_args[0]
        self.assertEqual(args[0], "TestCal")
        self.assertEqual(args[1], "2026-01-20")
        self.assertIn("A / B", args[2])

if __name__ == "__main__":
    unittest.main()
