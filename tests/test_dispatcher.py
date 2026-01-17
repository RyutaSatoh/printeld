import unittest
import shutil
import tempfile
import json
from pathlib import Path
from print_etl_d.dispatcher import Dispatcher
from print_etl_d.config import ActionConfig

class TestDispatcher(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.output_file = self.test_dir / "output.json"
        self.dispatcher = Dispatcher()

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir)

    async def test_save_json_append(self):
        action = ActionConfig(type="save_json", path=str(self.output_file))
        
        data1 = {"id": 1, "val": "a"}
        data2 = {"id": 2, "val": "b"}
        
        # Dispatch first item
        await self.dispatcher.dispatch([action], data1, Path("dummy.pdf"))
        
        # Verify file creation and content
        self.assertTrue(self.output_file.exists())
        with open(self.output_file, "r") as f:
            content = json.load(f)
            self.assertEqual(len(content), 1)
            self.assertEqual(content[0], data1)
            
        # Dispatch second item
        await self.dispatcher.dispatch([action], data2, Path("dummy.pdf"))
        
        # Verify append
        with open(self.output_file, "r") as f:
            content = json.load(f)
            self.assertEqual(len(content), 2)
            self.assertEqual(content[1], data2)

    async def test_move_file_copy(self):
        # Setup source file
        source_file = self.test_dir / "source.pdf"
        source_file.write_text("fake pdf content")
        
        dest_dir = self.test_dir / "dest"
        action = ActionConfig(
            type="move_file",
            base_dir=str(dest_dir),
            path_template="{category}/{date}_{topic}{extension}"
        )
        
        data = {
            "category": "cat1",
            "date": "20260120",
            "topic": "mytopic"
        }
        
        # Dispatch
        await self.dispatcher.dispatch([action], data, source_file)
        
        # Verify
        expected_path = dest_dir / "cat1" / "20260120_mytopic.pdf"
        self.assertTrue(expected_path.exists())
        self.assertEqual(expected_path.read_text(), "fake pdf content")
        # Ensure source still exists (it's a copy)
        self.assertTrue(source_file.exists())

if __name__ == "__main__":
    unittest.main()