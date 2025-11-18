#!/usr/bin/env python3
"""
Sports Betting Edge Toolkit - Main Entry Point
==============================================

Usage:
    python run.py dashboard     # Launch web dashboard
    python run.py scan          # Run EV/Arb scanner once
    python run.py monitor       # Run continuous monitoring with scheduler
    python run.py bot           # Start Telegram bot
"""

import sys
import os
import asyncio
import argparse
import yaml
from dotenv import load_dotenv

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

# Add to path
sys.path.insert(0, '.')


def load_config() -> dict:
    """Load configuration from YAML and environment."""
    config_path = 'config/config.yaml'

    if os.path.exists(config_path):
        with open(config_path) as f:
            config = yaml.safe_load(f)
    else:
        config = {}

    # Override with environment variables
    config['odds_api_key'] = os.getenv('ODDS_API_KEY', '')
    config['telegram'] = config.get('telegram', {})
    config['telegram']['bot_token'] = os.getenv('TELEGRAM_BOT_TOKEN', '')
    config['telegram']['chat_id'] = os.getenv('TELEGRAM_CHAT_ID', '')
    config['database_path'] = os.getenv('DATABASE_PATH', 'data/betting_edge.db')

    return config


def setup_logging(config: dict):
    """Set up logging based on config."""
    from src.logging_config import setup_logging as do_setup

    log_config = config.get('logging', {})

    do_setup(
        log_file=log_config.get('file', 'logs/betting_edge.log'),
        level=log_config.get('level', 'INFO'),
        telegram_token=config['telegram'].get('bot_token'),
        telegram_chat_id=config['telegram'].get('chat_id')
    )


def run_dashboard():
    """Launch Streamlit dashboard."""
    import subprocess
    subprocess.run([
        sys.executable, '-m', 'streamlit', 'run',
        'dashboard/app.py',
        '--server.port', '8501'
    ])


async def run_scan(config: dict, min_ev: float = 2.0, notify: bool = True):
    """Run single scan with new unified aggregator."""
    from src.scrapers.unified_odds_aggregator import UnifiedOddsAggregator
    from src.analyzers.ev_calculator import EVCalculator
    from src.analyzers.arbitrage_finder import ArbitrageFinder
    from src.notifications.telegram_bot import TelegramNotifier

    import logging
    logger = logging.getLogger(__name__)

    logger.info("Starting scan...")

    # Initialize aggregator
    aggregator = UnifiedOddsAggregator(config)

    try:
        # Fetch all odds
        events = await aggregator.aggregate_all()
        logger.info(f"Aggregated {len(events)} events")

        # Find +EV opportunities
        ev_config = config.get('ev_detection', {})
        ev_config['min_ev_percentage'] = min_ev
        ev_calc = EVCalculator(ev_config)
        ev_opportunities = ev_calc.find_ev_opportunities(events, min_ev)

        logger.info(f"Found {len(ev_opportunities)} +EV opportunities")

        # Find arbitrage
        arb_config = config.get('arbitrage', {})
        arb_finder = ArbitrageFinder(arb_config)
        min_arb = arb_config.get('min_profit_percentage', 1.0)
        arb_opportunities = arb_finder.find_arbitrage(events, min_arb)

        logger.info(f"Found {len(arb_opportunities)} arbitrage opportunities")

        # Print results
        if ev_opportunities:
            print("\n" + "="*60)
            print("🎯 +EV OPPORTUNITIES")
            print("="*60)

            for opp in ev_opportunities[:10]:
                print(f"\n+{opp.ev_percentage:.1f}% EV")
                print(f"  {opp.event.home_team} vs {opp.event.away_team}")
                print(f"  {opp.selection} @ {opp.offered_odds} ({opp.bookmaker})")
                print(f"  Sharp: {opp.sharp_odds} | Stake: €{opp.recommended_stake}")

        if arb_opportunities:
            print("\n" + "="*60)
            print("💰 ARBITRAGE OPPORTUNITIES")
            print("="*60)

            for opp in arb_opportunities[:5]:
                print(f"\n{opp.profit_percentage:.2f}% profit")
                print(f"  {opp.event.home_team} vs {opp.event.away_team}")
                print(f"  Guaranteed: €{opp.guaranteed_profit:.2f}")
                for leg in opp.legs:
                    print(f"    {leg.selection} @ {leg.odds} ({leg.bookmaker}): €{leg.stake}")

        # API usage
        usage = aggregator.get_api_usage()
        if usage.get('requests_remaining'):
            print(f"\n📊 API requests remaining: {usage['requests_remaining']}")

        # Send notifications
        if notify and (ev_opportunities or arb_opportunities):
            notifier = TelegramNotifier(config.get('telegram', {}))

            if ev_opportunities:
                await notifier.notify_multiple_ev(ev_opportunities[:5])

            for arb in arb_opportunities[:3]:
                await notifier.notify_arbitrage(arb)

            logger.info("Notifications sent")

        return ev_opportunities, arb_opportunities

    finally:
        await aggregator.close()


def run_monitor(config: dict):
    """Run continuous monitoring with scheduler."""
    from src.scheduler import run_scheduler

    run_scheduler(config)


def run_bot(config: dict):
    """Run Telegram bot."""
    from src.notifications.telegram_bot import BettingBot

    bot = BettingBot(config.get('telegram', {}))
    bot.run()


def main():
    parser = argparse.ArgumentParser(
        description='Sports Betting Edge Toolkit',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py dashboard           # Start web dashboard
  python run.py scan --min-ev 3     # Scan for 3%+ EV
  python run.py monitor             # 24/7 monitoring with scheduler
  python run.py bot                 # Interactive Telegram bot
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Dashboard
    dash_parser = subparsers.add_parser('dashboard', help='Launch web dashboard')

    # Scan
    scan_parser = subparsers.add_parser('scan', help='Run single scan')
    scan_parser.add_argument('--min-ev', type=float, default=2.0,
                             help='Minimum EV percentage')
    scan_parser.add_argument('--no-notify', action='store_true',
                             help='Disable Telegram notifications')

    # Monitor
    mon_parser = subparsers.add_parser('monitor', help='Continuous monitoring')

    # Bot
    bot_parser = subparsers.add_parser('bot', help='Telegram bot')

    args = parser.parse_args()

    # Load config
    config = load_config()

    # Setup logging
    setup_logging(config)

    if args.command == 'dashboard':
        run_dashboard()
    elif args.command == 'scan':
        asyncio.run(run_scan(config, args.min_ev, not args.no_notify))
    elif args.command == 'monitor':
        run_monitor(config)
    elif args.command == 'bot':
        run_bot(config)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
