#!/usr/bin/env python3
"""
Sports Betting Edge Toolkit - Main Entry Point
==============================================

Usage:
    python run.py dashboard     # Launch web dashboard
    python run.py scan          # Run EV/Arb scanner once
    python run.py monitor       # Run continuous monitoring
    python run.py bot           # Start Telegram bot
"""

import sys
import os
import asyncio
import argparse

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def run_dashboard():
    """Launch Streamlit dashboard."""
    import subprocess
    subprocess.run([
        sys.executable, '-m', 'streamlit', 'run',
        'dashboard/app.py',
        '--server.port', '8501'
    ])


async def run_scan(min_ev=2.0, notify=True):
    """Run single scan."""
    from scripts.run_scanner import run_scan as scanner
    return await scanner(min_ev=min_ev, notify=notify)


async def run_monitor(interval=60):
    """Run continuous monitoring."""
    from scripts.run_scanner import run_continuous
    await run_continuous(interval)


def run_bot():
    """Run Telegram bot."""
    from src.notifications.telegram_bot import BettingBot
    bot = BettingBot()
    bot.run()


def main():
    parser = argparse.ArgumentParser(
        description='Sports Betting Edge Toolkit',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py dashboard           # Start web dashboard
  python run.py scan --min-ev 3     # Scan for 3%+ EV
  python run.py monitor             # 24/7 monitoring
  python run.py bot                 # Telegram bot
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Dashboard
    dash_parser = subparsers.add_parser('dashboard', help='Launch web dashboard')

    # Scan
    scan_parser = subparsers.add_parser('scan', help='Run single scan')
    scan_parser.add_argument('--min-ev', type=float, default=2.0)
    scan_parser.add_argument('--no-notify', action='store_true')

    # Monitor
    mon_parser = subparsers.add_parser('monitor', help='Continuous monitoring')
    mon_parser.add_argument('--interval', type=int, default=60)

    # Bot
    bot_parser = subparsers.add_parser('bot', help='Telegram bot')

    args = parser.parse_args()

    if args.command == 'dashboard':
        run_dashboard()
    elif args.command == 'scan':
        asyncio.run(run_scan(args.min_ev, not args.no_notify))
    elif args.command == 'monitor':
        asyncio.run(run_monitor(args.interval))
    elif args.command == 'bot':
        run_bot()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
