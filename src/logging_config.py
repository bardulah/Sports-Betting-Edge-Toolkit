"""
Logging Configuration
=====================

Configures logging with file output and Telegram alerts for errors.
"""

import logging
import logging.handlers
import os
import asyncio
from typing import Optional


class TelegramHandler(logging.Handler):
    """
    Logging handler that sends errors to Telegram.
    """

    def __init__(self, bot_token: str, chat_id: str):
        super().__init__()
        self.bot_token = bot_token
        self.chat_id = chat_id

    def emit(self, record):
        if not self.bot_token or not self.chat_id:
            return

        try:
            log_entry = self.format(record)

            # Truncate if too long
            if len(log_entry) > 4000:
                log_entry = log_entry[:4000] + "..."

            # Send async
            asyncio.create_task(self._send(log_entry))
        except Exception:
            self.handleError(record)

    async def _send(self, message: str):
        import aiohttp

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            'chat_id': self.chat_id,
            'text': f"⚠️ <b>Error Alert</b>\n\n<code>{message}</code>",
            'parse_mode': 'HTML'
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    pass
        except:
            pass


def setup_logging(
    log_file: str = "logs/betting_edge.log",
    level: str = "INFO",
    telegram_token: str = None,
    telegram_chat_id: str = None
):
    """
    Set up logging with file and console output.

    Args:
        log_file: Path to log file
        level: Logging level
        telegram_token: Telegram bot token for error alerts
        telegram_chat_id: Telegram chat ID for alerts
    """
    # Create logs directory
    os.makedirs(os.path.dirname(log_file) if os.path.dirname(log_file) else '.', exist_ok=True)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Telegram handler for errors
    if telegram_token and telegram_chat_id:
        telegram_handler = TelegramHandler(telegram_token, telegram_chat_id)
        telegram_handler.setLevel(logging.ERROR)
        telegram_handler.setFormatter(formatter)
        root_logger.addHandler(telegram_handler)
        logging.info("Telegram error alerts enabled")

    # Reduce noise from libraries
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)

    logging.info(f"Logging configured: {level} level, file: {log_file}")
