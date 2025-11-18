#!/usr/bin/env python3
"""
Run Odds Scraper
================

Scrapes odds from all bookmakers and saves to database.
Can run once or continuously on a schedule.
"""

import asyncio
import argparse
import logging
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scrapers.odds_aggregator import OddsAggregator
from src.database.db_manager import DatabaseManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_scrape(sport: str = None, save_to_db: bool = True):
    """Run a single scrape."""
    logger.info("Starting odds scrape...")

    aggregator = OddsAggregator()

    try:
        results = await aggregator.scrape_all(sport)

        total_events = 0
        for sport_name, events in results.items():
            logger.info(f"{sport_name}: {len(events)} events")
            total_events += len(events)

        logger.info(f"Total events scraped: {total_events}")

        if save_to_db:
            db = DatabaseManager()
            # Save events and odds to database
            for sport_name, events in results.items():
                for event in events:
                    # Add event
                    event_id = db.add_event({
                        'sport': sport_name,
                        'league': event.league,
                        'home_team': event.home_team,
                        'away_team': event.away_team,
                        'start_time': event.start_time,
                        'external_id': event.external_id
                    })

                    # Add odds
                    for market_type, selections in event.odds.items():
                        for selection, odds_value in selections.items():
                            book = db.get_bookmaker(event.bookmaker.lower())
                            if book:
                                db.add_odds({
                                    'event_id': event_id,
                                    'bookmaker_id': book.id,
                                    'market_type': market_type,
                                    'selection': selection,
                                    'odds_value': odds_value
                                })

            logger.info("Saved to database")

        return results

    except Exception as e:
        logger.error(f"Scrape failed: {e}")
        raise


async def run_continuous(interval: int = 60, sport: str = None):
    """Run scraper continuously."""
    logger.info(f"Starting continuous scraping (interval: {interval}s)")

    while True:
        try:
            await run_scrape(sport)
        except Exception as e:
            logger.error(f"Scrape iteration failed: {e}")

        logger.info(f"Sleeping for {interval} seconds...")
        await asyncio.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description='Run odds scraper')
    parser.add_argument(
        '--sport',
        choices=['football', 'hockey', 'tennis'],
        help='Specific sport to scrape'
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
        help='Scrape interval in seconds (default: 60)'
    )
    parser.add_argument(
        '--no-save',
        action='store_true',
        help='Do not save to database'
    )

    args = parser.parse_args()

    if args.continuous:
        asyncio.run(run_continuous(args.interval, args.sport))
    else:
        asyncio.run(run_scrape(args.sport, not args.no_save))


if __name__ == '__main__':
    main()
