import sys
import asyncio
import shutil
import signal
from pathlib import Path
from loguru import logger

from print_etl_d.config import load_config, AppConfig, ProfileConfig
from print_etl_d.utils import setup_logging
from print_etl_d.watcher import WatcherService
from print_etl_d.processor import LLMProcessor, ProcessorError
from print_etl_d.dispatcher import Dispatcher

async def process_event(
    file_path: Path, 
    profile: ProfileConfig, 
    processor: LLMProcessor, 
    dispatcher: Dispatcher,
    config: AppConfig
):
    """
    Process a single file event.
    """
    try:
        # 1. Process with LLM
        logger.info(f"Processing {file_path.name} with profile '{profile.name}'")
        extracted_data = await processor.process_file(file_path, profile)
        
        # 2. Add metadata
        extracted_data["_source_file"] = file_path.name
        extracted_data["_profile"] = profile.name
        extracted_data["_timestamp"] = asyncio.get_event_loop().time() # Or datetime

        # 3. Dispatch Actions
        logger.info(f"Dispatching actions for {file_path.name}")
        await dispatcher.dispatch(profile.actions, extracted_data, file_path)
        
        # 4. Move to processed
        dest = config.system.processed_dir / file_path.name
        # Handle duplicates
        if dest.exists():
            timestamp = int(asyncio.get_event_loop().time())
            dest = config.system.processed_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"
            
        shutil.move(str(file_path), str(dest))
        logger.success(f"Successfully processed and moved to {dest}")

    except Exception as e:
        logger.error(f"Failed to process {file_path.name}: {e}")
        # Move to error dir
        dest = config.system.error_dir / file_path.name
        if dest.exists():
             timestamp = int(asyncio.get_event_loop().time())
             dest = config.system.error_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"
        
        try:
            shutil.move(str(file_path), str(dest))
            logger.info(f"Moved failed file to {dest}")
        except Exception as move_err:
            logger.error(f"Failed to move failed file: {move_err}")

async def worker(queue: asyncio.Queue, processor: LLMProcessor, dispatcher: Dispatcher, config: AppConfig):
    """
    Worker task to consume events from the queue.
    """
    logger.info("Worker started.")
    while True:
        try:
            # Wait for an item from the queue
            item = await queue.get()
            if item is None:
                # Signal to stop
                break
                
            file_path, profile = item
            
            # Ensure file still exists (it might have been moved if queue is backed up, though unlikely with move)
            if file_path.exists():
                await process_event(file_path, profile, processor, dispatcher, config)
            else:
                logger.warning(f"File {file_path} no longer exists. Skipping.")
            
            queue.task_done()
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.critical(f"Unhandled error in worker: {e}")

async def main_async():
    setup_logging()
    logger.info("Starting Print-ETL-D...")

    try:
        config = load_config("config.yaml")
        logger.info(f"Loaded configuration. Watch dir: {config.system.watch_dir}")
        
        queue = asyncio.Queue()
        
        # Initialize components
        watcher = WatcherService(config, queue)
        processor = LLMProcessor(config.system)
        dispatcher = Dispatcher()
        
        # Start Watcher
        watcher.start()
        
        # Start Worker
        worker_task = asyncio.create_task(worker(queue, processor, dispatcher, config))
        
        # Handle Shutdown Signals
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        
        def signal_handler():
            logger.info("Shutdown signal received.")
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)
            
        # Wait for stop signal
        await stop_event.wait()
        
        # Shutdown sequence
        logger.info("Shutting down...")
        watcher.stop()
        
        # Stop worker
        await queue.put(None)
        await worker_task
        
        logger.info("Goodbye.")
        
    except Exception as e:
        logger.critical(f"Application failed: {e}")
        sys.exit(1)

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass # Handled in async main

if __name__ == "__main__":
    main()