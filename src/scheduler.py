"""
Background Scheduler
====================

APScheduler-based job scheduling for:
- Periodic odds scraping
- CLV capture before events start
- Cleanup jobs
- Telegram notifications
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from .scrapers.unified_odds_aggregator import UnifiedOddsAggregator
from .analyzers.ev_calculator import EVCalculator
from .analyzers.arbitrage_finder import ArbitrageFinder
from .database.db_manager import DatabaseManager
from .notifications.telegram_bot import TelegramNotifier

logger = logging.getLogger(__name__)


class BettingScheduler:
    """
    Manages all background jobs for the betting toolkit.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}

        # Initialize scheduler
        self.scheduler = AsyncIOScheduler()

        # Initialize components
        self.aggregator = UnifiedOddsAggregator(self.config)
        self.ev_calculator = EVCalculator(self.config.get('ev_detection', {}))
        self.arb_finder = ArbitrageFinder(self.config.get('arbitrage', {}))
        self.db = DatabaseManager(self.config.get('database_path', 'data/betting_edge.db'))
        self.notifier = TelegramNotifier(self.config.get('telegram', {}))

        # Track scheduled CLV jobs
        self.clv_jobs = {}

    def start(self):
        """Start the scheduler with all jobs."""
        logger.info("Starting scheduler...")

        # Job 1: Periodic odds scraping
        scrape_interval = self.config.get('scraping', {}).get('interval_seconds', 60)
        self.scheduler.add_job(
            self.job_scrape_odds,
            trigger=IntervalTrigger(seconds=scrape_interval),
            id='scrape_odds',
            name='Scrape odds from all sources',
            max_instances=1,
            replace_existing=True
        )

        # Job 2: Find opportunities
        self.scheduler.add_job(
            self.job_find_opportunities,
            trigger=IntervalTrigger(seconds=scrape_interval + 5),
            id='find_opportunities',
            name='Find EV and arbitrage opportunities',
            max_instances=1,
            replace_existing=True
        )

        # Job 3: Schedule CLV captures (runs every 5 minutes)
        self.scheduler.add_job(
            self.job_schedule_clv_captures,
            trigger=IntervalTrigger(minutes=5),
            id='schedule_clv',
            name='Schedule CLV capture jobs',
            max_instances=1,
            replace_existing=True
        )

        # Job 4: Cleanup old data (daily at 3 AM)
        self.scheduler.add_job(
            self.job_cleanup,
            trigger=CronTrigger(hour=3, minute=0),
            id='cleanup',
            name='Cleanup old data',
            max_instances=1,
            replace_existing=True
        )

        # Job 5: Daily summary (at 9 PM)
        self.scheduler.add_job(
            self.job_daily_summary,
            trigger=CronTrigger(hour=21, minute=0),
            id='daily_summary',
            name='Send daily summary',
            max_instances=1,
            replace_existing=True
        )

        self.scheduler.start()
        logger.info(f"Scheduler started with {len(self.scheduler.get_jobs())} jobs")

    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")

    async def job_scrape_odds(self):
        """Scrape odds from all sources."""
        logger.info("Running odds scrape job...")

        try:
            events = await self.aggregator.aggregate_all()
            logger.info(f"Scraped {len(events)} events")

            # Log API usage
            usage = self.aggregator.get_api_usage()
            if usage.get('requests_remaining'):
                logger.info(f"API requests remaining: {usage['requests_remaining']}")

        except Exception as e:
            logger.error(f"Scrape job failed: {e}")
            await self.notifier.send_message(
                f"⚠️ <b>Scrape job failed</b>\n\n{str(e)}"
            )

    async def job_find_opportunities(self):
        """Find EV and arbitrage opportunities."""
        logger.info("Running opportunity finder...")

        try:
            # Get latest events from DB or scrape
            events = await self.aggregator.aggregate_all()

            # Find +EV opportunities
            min_ev = self.config.get('ev_detection', {}).get('min_ev_percentage', 2.0)
            ev_opportunities = self.ev_calculator.find_ev_opportunities(events, min_ev)

            if ev_opportunities:
                logger.info(f"Found {len(ev_opportunities)} +EV opportunities")

                # Notify top opportunities
                await self.notifier.notify_multiple_ev(ev_opportunities[:5])

                # Save to database
                for opp in ev_opportunities:
                    self.db.add_ev_opportunity({
                        'sport': opp.event.sport,
                        'league': opp.event.league,
                        'home_team': opp.event.home_team,
                        'away_team': opp.event.away_team,
                        'start_time': opp.event.start_time,
                        'bookmaker': opp.bookmaker,
                        'market_type': opp.market_type,
                        'selection': opp.selection,
                        'offered_odds': opp.offered_odds,
                        'sharp_odds': opp.sharp_odds,
                        'true_probability': opp.true_probability,
                        'ev_percentage': opp.ev_percentage,
                        'edge': opp.edge,
                        'kelly_stake': opp.kelly_stake,
                        'recommended_stake': opp.recommended_stake,
                        'detected_at': datetime.now()
                    })

            # Find arbitrage
            min_arb = self.config.get('arbitrage', {}).get('min_profit_percentage', 1.0)
            arb_opportunities = self.arb_finder.find_arbitrage(events, min_arb)

            if arb_opportunities:
                logger.info(f"Found {len(arb_opportunities)} arbitrage opportunities")

                # Notify
                for opp in arb_opportunities[:3]:
                    await self.notifier.notify_arbitrage(opp)

        except Exception as e:
            logger.error(f"Opportunity finder failed: {e}")

    async def job_schedule_clv_captures(self):
        """Schedule CLV capture jobs for upcoming events."""
        logger.info("Scheduling CLV captures...")

        try:
            # Get pending bets
            pending_bets = self.db.get_pending_bets()

            for bet in pending_bets:
                if not bet.event:
                    continue

                # Schedule capture 5 minutes before start
                capture_time = bet.event.start_time - timedelta(minutes=5)

                # Skip if already passed or too far in future
                now = datetime.now()
                if capture_time <= now:
                    continue
                if capture_time > now + timedelta(hours=24):
                    continue

                job_id = f"clv_capture_{bet.id}"

                # Skip if already scheduled
                if job_id in self.clv_jobs:
                    continue

                self.scheduler.add_job(
                    self.job_capture_clv,
                    trigger=DateTrigger(run_date=capture_time),
                    args=[bet.id],
                    id=job_id,
                    name=f'CLV capture for bet {bet.id}',
                    max_instances=1
                )

                self.clv_jobs[job_id] = True
                logger.info(f"Scheduled CLV capture for bet {bet.id} at {capture_time}")

        except Exception as e:
            logger.error(f"Failed to schedule CLV captures: {e}")

    async def job_capture_clv(self, bet_id: int):
        """Capture closing odds for a bet."""
        logger.info(f"Capturing CLV for bet {bet_id}...")

        try:
            bet = self.db.get_bet(bet_id)
            if not bet or not bet.event:
                return

            # Scrape current odds
            events = await self.aggregator.aggregate_all()

            # Find matching event
            for event in events:
                if (event.home_team == bet.event.home_team and
                    event.away_team == bet.event.away_team):

                    # Get closing odds from same bookmaker
                    book_odds = event.bookmaker_odds.get(bet.bookmaker.code, {})
                    closing_odds = book_odds.get('h2h', {}).get(bet.selection)

                    # Get Pinnacle closing
                    pinnacle_odds = event.bookmaker_odds.get('pinnacle', {}).get('h2h', {})
                    pinnacle_closing = pinnacle_odds.get(bet.selection)

                    if closing_odds:
                        # Calculate CLV
                        from .utils.probability_utils import ProbabilityUtils
                        clv = ProbabilityUtils.calculate_clv(bet.odds, closing_odds)

                        # Update bet
                        self.db.update_bet(bet_id, {
                            'closing_odds': closing_odds,
                            'clv': clv
                        })

                        logger.info(f"Bet {bet_id} CLV: {clv}%")

                        # Notify if beat the line
                        if clv > 0:
                            await self.notifier.notify_clv_beat({
                                'event': f"{bet.event.home_team} vs {bet.event.away_team}",
                                'selection': bet.selection,
                                'bet_odds': bet.odds,
                                'closing_odds': closing_odds,
                                'clv': clv
                            })

                        # Save CLV record
                        self.db.add_clv_record({
                            'bet_id': bet_id,
                            'event_id': bet.event.id,
                            'bookmaker': bet.bookmaker.code,
                            'selection': bet.selection,
                            'bet_odds': bet.odds,
                            'closing_odds': closing_odds,
                            'pinnacle_closing': pinnacle_closing,
                            'clv_vs_close': clv
                        })

                    break

        except Exception as e:
            logger.error(f"CLV capture failed for bet {bet_id}: {e}")

    async def job_cleanup(self):
        """Cleanup old data."""
        logger.info("Running cleanup job...")

        try:
            # Deactivate old opportunities
            self.db.deactivate_old_ev_opportunities(hours=24)

            logger.info("Cleanup complete")

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

    async def job_daily_summary(self):
        """Send daily summary to Telegram."""
        logger.info("Sending daily summary...")

        try:
            # Get today's stats
            today = datetime.now().replace(hour=0, minute=0, second=0)
            stats = self.db.get_betting_stats(start_date=today)
            clv_stats = self.db.get_clv_stats(today)

            message = (
                "<b>📊 Daily Summary</b>\n\n"
                f"Bets today: {stats['total_bets']}\n"
                f"Win rate: {stats['win_rate']}%\n"
                f"P/L: €{stats['profit_loss']:+.2f}\n"
                f"ROI: {stats['roi']:+.1f}%\n"
                f"Avg CLV: {clv_stats.get('avg_clv', 0):+.1f}%\n\n"
                f"<i>API requests remaining: {self.aggregator.get_api_usage().get('requests_remaining', 'N/A')}</i>"
            )

            await self.notifier.send_message(message)

        except Exception as e:
            logger.error(f"Daily summary failed: {e}")

    def add_custom_job(
        self,
        func,
        trigger,
        job_id: str,
        name: str = None,
        **kwargs
    ):
        """Add a custom job to the scheduler."""
        self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=name or job_id,
            **kwargs
        )


def run_scheduler(config: dict = None):
    """Run the scheduler (blocking)."""
    import signal

    scheduler = BettingScheduler(config)
    scheduler.start()

    # Handle shutdown
    def shutdown(signum, frame):
        logger.info("Shutting down...")
        scheduler.stop()
        exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Keep running
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        scheduler.stop()
