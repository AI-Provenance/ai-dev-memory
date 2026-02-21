import logging
import sys
import os
from typing import Optional
from pathlib import Path


def get_log_level() -> str:
    return os.environ.get("DEVMEMORY_LOG_LEVEL", "WARNING").upper()


def get_log_file() -> Optional[str]:
    return os.environ.get("DEVMEMORY_LOG_FILE")


def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[str] = None,
) -> logging.Logger:
    log_level = (level or get_log_level()).upper()
    file_path = log_file or get_log_file()

    logger = logging.getLogger("devmemory")
    logger.setLevel(getattr(logging, log_level, logging.WARNING))
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)

    if file_path:
        try:
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(file_path)
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
            )
            logger.addHandler(file_handler)
        except Exception:
            pass

    return logger


_initialized = False


def get_logger(name: str = "devmemory") -> logging.Logger:
    global _initialized
    if not _initialized:
        setup_logging()
        _initialized = True
    return logging.getLogger(name)
