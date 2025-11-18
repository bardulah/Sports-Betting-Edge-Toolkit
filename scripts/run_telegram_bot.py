#!/usr/bin/env python3
"""
Run Telegram Bot
================

Interactive Telegram bot for betting management.
"""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.notifications.telegram_bot import BettingBot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def main():
    bot = BettingBot()
    bot.run()


if __name__ == '__main__':
    main()
