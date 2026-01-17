import yaml
from pathlib import Path
from typing import Dict, List, Optional, Literal, Any
from pydantic import BaseModel, Field, ValidationError
from loguru import logger

class FieldDefinition(BaseModel):
    """Definition of a field to extract."""
    type: str
    description: str
    # For object types or list of objects
    properties: Optional[Dict[str, "FieldDefinition"]] = None 
    # For list types (if we want to define structure of items explicitly beyond simple types)
    items: Optional["FieldDefinition"] = None

class ActionConfig(BaseModel):
    """Configuration for an action to perform after extraction."""
    type: Literal["webhook", "save_json", "move_file", "add_caldav_event"]
    url: Optional[str] = None
    path: Optional[str] = None
    # For move_file action
    base_dir: Optional[str] = None
    path_template: Optional[str] = None
    # For add_caldav_event action
    calendar_url: Optional[str] = None
    username_env: Optional[str] = None
    password_env: Optional[str] = None
    summary_template: Optional[str] = None
    calendar_map: Optional[Dict[str, str]] = None # e.g. {"りっちゃん": "Ricchan"}

class ProfileConfig(BaseModel):
    """Configuration for a processing profile."""
    name: str
    match_pattern: str
    description: str
    fields: Dict[str, FieldDefinition]
    actions: List[ActionConfig] = Field(default_factory=list)

class SystemConfig(BaseModel):
    """System-wide configuration."""
    watch_dir: Path
    processed_dir: Path
    error_dir: Path
    gemini_model: str = "gemini-1.5-flash"
    scan_interval_sec: float = 1.0

class AppConfig(BaseModel):
    """Root configuration object."""
    system: SystemConfig
    profiles: List[ProfileConfig]

from print_etl_d.utils import load_categories_context

def load_config(config_path: str = "config.yaml") -> AppConfig:
    """
    Load and validate configuration from a YAML file.
    """
    path = Path(config_path)
    if not path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        config = AppConfig(**data)

        # Ensure directories exist
        config.system.watch_dir.mkdir(parents=True, exist_ok=True)
        config.system.processed_dir.mkdir(parents=True, exist_ok=True)
        config.system.error_dir.mkdir(parents=True, exist_ok=True)

        # Inject dynamic categories if available
        # Categories are now in the project root
        categories_dir = Path("categories")
        categories_context = load_categories_context(categories_dir)

        if categories_context:
            for profile in config.profiles:
                if "category_folder" in profile.fields:
                    original_desc = profile.fields["category_folder"].description
                    profile.fields["category_folder"].description = f"{original_desc}\n\n{categories_context}"
                    logger.info(f"Injected category definitions into profile '{profile.name}'")

        logger.info(f"Configuration loaded successfully from {config_path}")
        return config

    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file: {e}")
        raise
    except ValidationError as e:
        logger.error(f"Configuration validation error: {e}")
        raise
