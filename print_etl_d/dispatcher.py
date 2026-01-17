import json
import asyncio
import os
import shutil
from pathlib import Path
from typing import Dict, Any, List
import httpx
from loguru import logger
from print_etl_d.config import ActionConfig
from print_etl_d.caldav_sync import CalDAVSyncManager

class Dispatcher:
    async def dispatch(self, actions: List[ActionConfig], data: Dict[str, Any], source_file: Path):
        """
        Dispatch data to all configured actions.
        Args:
            source_file: Path to the original file being processed.
        """
        for action in actions:
            try:
                if action.type == "save_json":
                    await self._save_json(action, data)
                elif action.type == "webhook":
                    await self._send_webhook(action, data)
                elif action.type == "move_file":
                    await self._move_file(action, data, source_file)
                elif action.type == "add_caldav_event":
                    await self._add_caldav_event(action, data, source_file)
                else:
                    logger.warning(f"Unknown action type: {action.type}")
            except Exception as e:
                logger.error(f"Failed to execute action {action.type}: {e}")

    async def _add_caldav_event(self, action: ActionConfig, data: Dict[str, Any], source_file: Path):
        """
        Delegate event creation to CalDAVSyncManager.
        """
        if not action.calendar_url or not action.username_env or not action.password_env:
            logger.warning("Action add_caldav_event missing connection details.")
            return

        username = os.getenv(action.username_env)
        password = os.getenv(action.password_env)
        if not username or not password:
            logger.error(f"CalDAV credentials not found in env: {action.username_env}")
            return

        # Determine Target Calendar
        category = data.get("category_folder", "")
        clean_category = category.replace("【", "").replace("】", "").strip()
        
        target_cal_name = None
        if action.calendar_map and clean_category in action.calendar_map:
            target_cal_name = action.calendar_map[clean_category]
        else:
            logger.info(f"No calendar mapping found for category '{clean_category}'. Skipping CalDAV sync.")
            return

        # Prepare Data
        details = data.get("school_details")
        if not details or not isinstance(details, dict):
            logger.debug("No school_details found to sync.")
            return
            
        schedule_list = details.get("schedule_list", [])
        if not schedule_list:
            return

        # Run Sync
        # Using a new instance for each action call is simple and stateless.
        # Connection pooling could be an optimization for the future.
        manager = CalDAVSyncManager(action.calendar_url, username, password)
        
        # Run blocking operations in thread
        await asyncio.to_thread(self._process_schedule_list, manager, target_cal_name, schedule_list, source_file.name)

    def _process_schedule_list(self, manager, target_cal_name, schedule_list, source_filename):
        """Worker function to process the list synchronously."""
        if not manager.connect():
            return

        for item in schedule_list:
            event_date_str = item.get("date")
            if not event_date_str:
                continue
            
            # Format Summary
            special = item.get("special_items", [])
            irregular = item.get("irregular_schedule")
            
            summary_parts = []
            if special:
                if isinstance(special, list):
                    summary_parts.extend(special)
                else:
                    summary_parts.append(str(special))
            if irregular and irregular != "null":
                summary_parts.append(irregular)
            
            if not summary_parts:
                continue
                
            summary = " / ".join(summary_parts)
            description = f"Extracted from {source_filename}"
            
            manager.sync_event(target_cal_name, event_date_str, summary, description)

    async def _move_file(self, action: ActionConfig, data: Dict[str, Any], source_file: Path):
        """
        Copy the source file to a new location based on template.
        """
        if not action.base_dir or not action.path_template:
            logger.warning("Action move_file missing base_dir or path_template.")
            return

        try:
            safe_data = {k: str(v).replace("/", "_").replace("\\", "_") for k, v in data.items() if v is not None}
            safe_data["original_name"] = source_file.stem
            safe_data["extension"] = source_file.suffix

            relative_path = action.path_template.format(**safe_data)
            dest_path = Path(action.base_dir) / relative_path
            
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            counter = 1
            original_dest = dest_path
            while dest_path.exists():
                stem = original_dest.stem
                suffix = original_dest.suffix
                dest_path = original_dest.with_name(f"{stem}_{counter}{suffix}")
                counter += 1
                
            shutil.copy2(source_file, dest_path)
            logger.info(f"Copied and renamed file to: {dest_path}")
            
        except KeyError as ke:
             logger.error(f"Missing key for path template: {ke}. Data keys: {list(data.keys())}")
        except Exception as e:
             logger.error(f"Error in move_file: {e}")

    async def _save_json(self, action: ActionConfig, data: Dict[str, Any]):
        if not action.path:
            logger.warning("Action save_json missing path configuration.")
            return

        path = Path(action.path)
        path.parent.mkdir(parents=True, exist_ok=True)

        current_data = []
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if content.strip():
                        loaded = json.loads(content)
                        if isinstance(loaded, list):
                            current_data = loaded
                        else:
                            current_data = [loaded]
            except json.JSONDecodeError:
                logger.warning(f"File {path} exists but is not valid JSON.")
            except Exception as e:
                logger.error(f"Error reading {path}: {e}")

        current_data.append(data)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Saved data to {path}")

    async def _send_webhook(self, action: ActionConfig, data: Dict[str, Any]):
        if not action.url:
            logger.warning("Action webhook missing url configuration.")
            return

        async with httpx.AsyncClient() as client:
            response = await client.post(action.url, json=data)
            response.raise_for_status()
            logger.info(f"Webhook sent to {action.url}. Status: {response.status_code}")