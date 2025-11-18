#!/usr/bin/env python3
"""
Run EV & Arbitrage Scanner
==========================

Scans for +EV opportunities and arbitrage, sends notifications.
"""

import asyncio
import argparse
import logging
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scrapers.odds_aggregator import OddsAggregator
from src.analyzers.ev_calculator import EVCalculator
from src.analyzers.arbitrage_finder import ArbitrageFinder
from src.notifications.telegram_bot import TelegramNotifier
from src.database.db_manager import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_scan(
    min_ev: float = 2.0,
    min_arb: float = 1.0,
    notify: bool = True
):
    """Run EV and arbitrage scan."""
    logger.info("Starting scan...")

    # Scrape odds
    aggregator = OddsAggregator()
    results = await aggregator.scrape_all()

    all_events = []
    for sport_events in results.values():
        all_events.extend(sport_events)

    logger.info(f"Scraped {len(all_events)} events")

    # Find EV opportunities
    ev_calc = EVCalculator({'min_ev_percentage': min_ev})
    ev_opportunities = ev_calc.find_ev_opportunities(all_events, min_ev)

    logger.info(f"Found {len(ev_opportunities)} +EV opportunities")

    # Find arbitrage
    arb_finder = ArbitrageFinder({'min_profit_percentage': min_arb})
    arb_opportunities = arb_finder.find_arbitrage(all_events, min_arb)

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

    # Send notifications
    if notify and (ev_opportunities or arb_opportunities):
        notifier = TelegramNotifier()

        if ev_opportunities:
            await notifier.notify_multiple_ev(ev_opportunities[:5])

        for arb in arb_opportunities[:3]:
            await notifier.notify_arbitrage(arb)

        logger.info("Notifications sent")

    return ev_opportunities, arb_opportunities


async def run_continuous(interval: int = 60, **kwargs):
    """Run scanner continuously."""
    logger.info(f"Starting continuous scanning (interval: {interval}s)")

    while True:
        try:
            await run_scan(**kwargs)
        except Exception as e:
            logger.error(f"Scan failed: {e}")

        logger.info(f"Next scan in {interval} seconds...")
        await asyncio.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description='Run EV/Arb scanner')
    parser.add_argument(
        '--min-ev',
        type=float,
        default=2.0,
        help='Minimum EV percentage (default: 2.0)'
    )
    parser.add_argument(
        '--min-arb',
        type=float,
        default=1.0,
        help='Minimum arb profit percentage (default: 1.0)'
    )
    parser.add_argument(
        '--continuous',
        action='store_true',
        help='Run continuously'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=60,
        help='Scan interval in seconds (default: 60)'
    )
    parser.add_argument(
        '--no-notify',
        action='store_true',
        help='Disable Telegram notifications'
    )

    args = parser.parse_args()

    kwargs = {
        'min_ev': args.min_ev,
        'min_arb': args.min_arb,
        'notify': not args.no_notify
    }

    if args.continuous:
        asyncio.run(run_continuous(args.interval, **kwargs))
    else:
        asyncio.run(run_scan(**kwargs))


if __name__ == '__main__':
    main()
