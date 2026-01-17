import json
import asyncio
import os
from pathlib import Path
from typing import Dict, Any, List
from datetime import date, datetime
import httpx
import caldav
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
                elif action.type == "add_caldav_event":
                    await self._add_caldav_event(action, data, source_file)
                else:
                    logger.warning(f"Unknown action type: {action.type}")
            except Exception as e:
                logger.error(f"Failed to execute action {action.type}: {e}")

    async def _add_caldav_event(self, action: ActionConfig, data: Dict[str, Any], source_file: Path):
        """
        Add events to CalDAV calendar based on extracted data.
        """
        if not action.calendar_url or not action.username_env or not action.password_env:
            logger.warning("Action add_caldav_event missing connection details.")
            return

        # 1. Get credentials
        username = os.getenv(action.username_env)
        password = os.getenv(action.password_env)
        if not username or not password:
            logger.error(f"CalDAV credentials not found in env: {action.username_env}, {action.password_env}")
            return

        # 2. Determine Target Calendar
        category = data.get("category_folder", "")
        # Sanitize category name (remove brackets if LLM included them)
        clean_category = category.replace("【", "").replace("】", "").strip()

        target_cal_name = None
        if action.calendar_map and clean_category in action.calendar_map:
            target_cal_name = action.calendar_map[clean_category]
        else:
            logger.info(f"No calendar mapping found for category '{clean_category}'. (Raw: '{category}') Skipping CalDAV sync.")
            return

        # 3. Connect to CalDAV
        try:
            # Run blocking CalDAV operations in a thread
            await asyncio.to_thread(self._sync_caldav_blocking, action, username, password, target_cal_name, data, source_file)

        except Exception as e:
            logger.error(f"CalDAV sync failed: {e}")

    def _sync_caldav_blocking(self, action, username, password, target_cal_name, data, source_file):
        """Blocking part of CalDAV sync."""
        try:
            client = caldav.DAVClient(
                url=action.calendar_url,
                username=username,
                password=password
            )
            principal = client.principal()
            calendars = principal.calendars()

            target_calendar = None
            for cal in calendars:
                try:
                    props = cal.get_properties([caldav.dav.DisplayName()])
                    display_name = props.get(caldav.dav.DisplayName(), "").strip('"')
                    if display_name == target_cal_name or cal.name == target_cal_name:
                        target_calendar = cal
                        break
                except:
                    # Fallback if properties fail
                    if cal.name == target_cal_name:
                         target_calendar = cal
                         break

            if not target_calendar:
                logger.error(f"Calendar '{target_cal_name}' not found on server.")
                return

            # 4. Process Schedule List
            details = data.get("school_details")
            if not details or not isinstance(details, dict):
                logger.debug("No school_details found to sync.")
                return

            schedule_list = details.get("schedule_list", [])
            if not schedule_list:
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

                # Create All Day Event
                try:
                    from datetime import timedelta
                    dt_start = datetime.strptime(event_date_str, "%Y-%m-%d")
                    dt_end = dt_start + timedelta(days=1)

                    dt_start_str = dt_start.strftime("%Y%m%d")
                    dt_end_str = dt_end.strftime("%Y%m%d")

                    # Generate a unique UID
                    import uuid
                    uid = str(uuid.uuid4())

                    # Construct raw iCalendar data with STRICT CRLF (\r\n)
                    # Note: f-strings with \r\n are handled by Python
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
                        f"DESCRIPTION:Extracted from {source_file.name}",
                        "END:VEVENT",
                        "END:VCALENDAR"
                    ]
                    vcal = "\r\n".join(vcal_lines) + "\r\n"

                    logger.debug(f"Attempting to add event to {target_calendar.url} on {event_date_str}")

                    # Duplicate check
                    is_duplicate = False
                    try:
                        search_dt = dt_start.date()
                        existing = target_calendar.date_search(start=search_dt, end=search_dt)
                        for ev in existing:
                            if summary in ev.data:
                                is_duplicate = True
                                break
                    except:
                        pass

                    if not is_duplicate:
                        target_calendar.add_event(vcal)
                        logger.info(f"Added event to {target_cal_name}: {event_date_str} - {summary}")
                    else:
                        logger.debug(f"Skipping duplicate event: {event_date_str} - {summary}")

                except Exception as e:
                    logger.error(f"Failed to add event for {event_date_str}: {e}")
        except Exception as e:
            import traceback
            logger.error(f"CalDAV client error: {e}")
            logger.debug(traceback.format_exc())

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
