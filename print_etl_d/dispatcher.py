import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List
import httpx
from loguru import logger
from print_etl_d.config import ActionConfig

import shutil
import os

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
                else:
                    logger.warning(f"Unknown action type: {action.type}")
            except Exception as e:
                logger.error(f"Failed to execute action {action.type}: {e}")

    async def _move_file(self, action: ActionConfig, data: Dict[str, Any], source_file: Path):
        """
        Copy the source file to a new location based on template.
        Actually performs a copy to preserve the original for the main loop to handle (move to processed).
        """
        if not action.base_dir or not action.path_template:
            logger.warning("Action move_file missing base_dir or path_template.")
            return

        try:
            # 1. Flatten data for easy formatting if needed, or just use data dict
            # Access nested keys might be needed? For now assume flat keys in template like {date}_{topic}
            # We add some safe defaults if keys are missing
            
            # Extract root level keys or specific known keys from nested objects
            # For simplicity, we expect top-level fields in data matching template placeholders
            
            # Format the path
            # We sanitize values to be filename safe
            safe_data = {k: str(v).replace("/", "_").replace("\\", "_") for k, v in data.items() if v is not None}
            
            # Add source filename parts if needed
            safe_data["original_name"] = source_file.stem
            safe_data["extension"] = source_file.suffix
            
            relative_path = action.path_template.format(**safe_data)
            dest_path = Path(action.base_dir) / relative_path
            
            # Create directories
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Handle duplicates
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
        
        # Lock file access if needed? For now, assume single worker processing.
        # Logic: Read existing, append, write.
        
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
                            # If it was a single object, convert to list
                            current_data = [loaded]
            except json.JSONDecodeError:
                logger.warning(f"File {path} exists but is not valid JSON. Overwriting/Resetting.")
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
            logger.debug(f"Sending webhook to {action.url}")
            response = await client.post(action.url, json=data)
            response.raise_for_status()
            logger.info(f"Webhook sent to {action.url}. Status: {response.status_code}")
