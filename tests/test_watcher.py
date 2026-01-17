import unittest
import asyncio
import shutil
import tempfile
from pathlib import Path
from print_etl_d.watcher import WatcherService
from print_etl_d.config import AppConfig, SystemConfig, ProfileConfig, FieldDefinition

class TestWatcherService(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.processed_dir = Path(tempfile.mkdtemp())
        self.error_dir = Path(tempfile.mkdtemp())
        
        self.system_config = SystemConfig(
            watch_dir=self.test_dir,
            processed_dir=self.processed_dir,
            error_dir=self.error_dir
        )
        
        self.profile = ProfileConfig(
            name="test_profile",
            match_pattern="*.txt",
            description="Test",
            fields={}
        )
        
        self.config = AppConfig(
            system=self.system_config,
            profiles=[self.profile]
        )
        
        self.queue = asyncio.Queue()
        self.watcher = WatcherService(self.config, self.queue)

    async def asyncTearDown(self):
        self.watcher.stop()
        shutil.rmtree(self.test_dir)
        shutil.rmtree(self.processed_dir)
        shutil.rmtree(self.error_dir)

    async def test_file_detection(self):
        # Start watcher
        self.watcher.start()
        
        # Create a matching file
        test_file = self.test_dir / "test.txt"
        test_file.touch()
        
        # Wait for queue to have item
        try:
            item = await asyncio.wait_for(self.queue.get(), timeout=2.0)
            file_path, profile = item
            
            self.assertEqual(file_path.name, "test.txt")
            self.assertEqual(profile.name, "test_profile")
            
        except asyncio.TimeoutError:
            self.fail("Timed out waiting for file event in queue")

    async def test_ignore_non_matching(self):
        self.watcher.start()
        
        # Create non-matching file
        test_file = self.test_dir / "ignore.log"
        test_file.touch()
        
        # Verify queue is empty after short delay
        try:
            await asyncio.wait_for(self.queue.get(), timeout=0.5)
            self.fail("Queue should be empty for non-matching file")
        except asyncio.TimeoutError:
            pass # Expected

if __name__ == "__main__":
    unittest.main()
