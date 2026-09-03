import sys
import os
from loguru import logger
from backend.config import settings

def setup_logger():
    # Remove default handler
    logger.remove()

    # Define log format
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # Console output
    logger.add(
        sys.stderr,
        format=log_format,
        level=settings.LOG_LEVEL,
        colorize=True
    )

    # Ensure logs directory exists
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)

    # File output (rotating, JSON formatted for structured audit trails)
    logger.add(
        os.path.join(log_dir, "volhelix.log"),
        format="{message}",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        serialize=True  # This makes it write JSON
    )

    # WebSocket output (custom sink)
    def websocket_sink(message):
        try:
            import requests
            record = message.record
            agent = record["name"]
            
            requests.post("http://localhost:8000/api/internal/log", json={
                "agent": agent.split('.')[-1],
                "message": record["message"],
                "level": record["level"].name
            }, timeout=0.5)
        except Exception:
            pass

    logger.add(websocket_sink, level="INFO")

setup_logger()

def get_logger(name: str):
    return logger.bind(module=name)
