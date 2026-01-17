import sys
from pathlib import Path
from loguru import logger

def setup_logging(level: str = "INFO"):
    """
    Configure loguru logger.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    # Ensure logs directory exists
    log_path = Path("logs/app.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_path,
        rotation="10 MB",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )

def load_categories_context(categories_dir: Path) -> str:
    """
    Load category definitions from text files in the specified directory.
    Returns a formatted string suitable for LLM prompt.
    """
    if not categories_dir.exists():
        logger.warning(f"Categories directory not found: {categories_dir}")
        return ""

    context_lines = ["以下はカテゴリとその定義です。この定義に基づいて最適なフォルダを選択してください："]

    for txt_file in categories_dir.glob("*.txt"):
        if txt_file.name.endswith("~"): # skip backup files
            continue

        category_name = txt_file.stem
        try:
            content = txt_file.read_text(encoding="utf-8").strip()
            # If content is empty, use name as keyword
            if not content:
                content = category_name

            # Collapse newlines for cleaner prompt
            content = content.replace("\n", " ").replace("\r", "")
            context_lines.append(f"- 【{category_name}】: {content}")
        except Exception as e:
            logger.warning(f"Failed to read category file {txt_file}: {e}")

    return "\n".join(context_lines)

# Default setup
setup_logging()