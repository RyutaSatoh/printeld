import time
import asyncio
from pathlib import Path
from typing import List, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

from loguru import logger
from print_etl_d.config import AppConfig, ProfileConfig

class FileQueueHandler(FileSystemEventHandler):
    """
    Watchdog handler that puts matching files into an asyncio Queue.
    """
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue, config: AppConfig):
        self.loop = loop
        self.queue = queue
        self.config = config

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_file_event(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        # src_path is the old location, dest_path is the new one
        self._handle_file_event(event.dest_path)

    def _handle_file_event(self, path_str: str):
        file_path = Path(path_str)
        logger.debug(f"File event detected: {file_path}")
        
        # Check if file matches any profile
        matched_profile = self._match_profile(file_path)
        if matched_profile:
            logger.info(f"File {file_path.name} matches profile '{matched_profile.name}'. Queuing...")
            
            # Put into asyncio queue thread-safely
            self.loop.call_soon_threadsafe(
                self.queue.put_nowait,
                (file_path, matched_profile)
            )
        else:
            logger.debug(f"File {file_path.name} does not match any profile. Ignoring.")

    def _match_profile(self, file_path: Path) -> Optional[ProfileConfig]:
        """Find the first profile that matches the file name."""
        for profile in self.config.profiles:
            if file_path.match(profile.match_pattern):
                return profile
        return None

class WatcherService:
    def __init__(self, config: AppConfig, queue: asyncio.Queue):
        self.config = config
        self.queue = queue
        self.observer = Observer()
        
    def start(self):
        """Start the directory watcher."""
        loop = asyncio.get_running_loop()
        event_handler = FileQueueHandler(loop, self.queue, self.config)
        
        watch_dir = self.config.system.watch_dir
        if not watch_dir.exists():
            logger.warning(f"Watch directory {watch_dir} does not exist. Creating it.")
            watch_dir.mkdir(parents=True, exist_ok=True)
            
        self.observer.schedule(event_handler, str(watch_dir), recursive=False)
        self.observer.start()
        logger.info(f"Watcher started on {watch_dir}")
        
    def stop(self):
        """Stop the watcher."""
        self.observer.stop()
        self.observer.join()
        logger.info("Watcher stopped.")
