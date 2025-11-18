"""
Odds Aggregator
===============

Aggregates odds from all bookmakers and matches events across books.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import logging
from difflib import SequenceMatcher

from .base_scraper import ScrapedEvent
from .tipsport import TipsportScraper
from .fortuna import FortunaScraper
from .nike import NikeScraper
from .doxxbet import DoxxbetScraper
from .pinnacle import PinnacleScraper
from .bet365 import Bet365Scraper


@dataclass
class AggregatedEvent:
    """Event with odds from multiple bookmakers."""
    sport: str
    league: str
    home_team: str
    away_team: str
    start_time: datetime
    bookmaker_odds: Dict[str, Dict[str, Dict[str, float]]] = field(default_factory=dict)
    # Format: {bookmaker: {market_type: {selection: odds}}}

    def get_best_odds(self, market: str = 'moneyline') -> Dict[str, Tuple[float, str]]:
        """Get best odds for each selection across all books."""
        best = {}

        for bookmaker, markets in self.bookmaker_odds.items():
            if market not in markets:
                continue

            for selection, odds in markets[market].items():
                if selection not in best or odds > best[selection][0]:
                    best[selection] = (odds, bookmaker)

        return best

    def get_all_odds(self, market: str = 'moneyline') -> Dict[str, List[Tuple[float, str]]]:
        """Get all odds for each selection with bookmaker names."""
        all_odds = {}

        for bookmaker, markets in self.bookmaker_odds.items():
            if market not in markets:
                continue

            for selection, odds in markets[market].items():
                if selection not in all_odds:
                    all_odds[selection] = []
                all_odds[selection].append((odds, bookmaker))

        # Sort by odds (highest first)
        for selection in all_odds:
            all_odds[selection].sort(key=lambda x: x[0], reverse=True)

        return all_odds

    def has_sharp_odds(self) -> bool:
        """Check if event has odds from a sharp bookmaker."""
        sharp_books = ['Pinnacle']
        return any(book in self.bookmaker_odds for book in sharp_books)

    def get_sharp_odds(self, market: str = 'moneyline') -> Optional[Dict[str, float]]:
        """Get odds from sharp bookmaker (Pinnacle)."""
        if 'Pinnacle' in self.bookmaker_odds:
            return self.bookmaker_odds['Pinnacle'].get(market, {})
        return None


class OddsAggregator:
    """
    Aggregates odds from multiple bookmakers and matches events.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("OddsAggregator")

        # Initialize all scrapers
        self.scrapers = {
            'tipsport': TipsportScraper(config),
            'fortuna': FortunaScraper(config),
            'nike': NikeScraper(config),
            'doxxbet': DoxxbetScraper(config),
            'pinnacle': PinnacleScraper(config),
            'bet365': Bet365Scraper(config),
        }

        # Which scrapers to use
        self.active_scrapers = self.config.get('active_scrapers', list(self.scrapers.keys()))

        # Matching thresholds
        self.team_match_threshold = 0.7
        self.time_window_minutes = 30

    async def scrape_all(self, sport: str = None) -> Dict[str, List[AggregatedEvent]]:
        """
        Scrape all bookmakers and aggregate events.

        Args:
            sport: Optional sport to scrape ('football', 'hockey', 'tennis')
                   If None, scrapes all sports

        Returns:
            Dictionary of {sport: [AggregatedEvent]}
        """
        sports = [sport] if sport else ['football', 'hockey', 'tennis']

        results = {}

        for s in sports:
            self.logger.info(f"Scraping {s} from all bookmakers...")

            # Scrape all bookmakers concurrently
            scraper_tasks = []
            scraper_names = []

            for name in self.active_scrapers:
                if name not in self.scrapers:
                    continue

                scraper = self.scrapers[name]

                if s == 'football':
                    task = scraper.scrape_football()
                elif s == 'hockey':
                    task = scraper.scrape_hockey()
                elif s == 'tennis':
                    task = scraper.scrape_tennis()
                else:
                    continue

                scraper_tasks.append(task)
                scraper_names.append(name)

            # Run all scrapers concurrently
            all_events = await asyncio.gather(*scraper_tasks, return_exceptions=True)

            # Collect events by bookmaker
            events_by_book = {}
            for name, events in zip(scraper_names, all_events):
                if isinstance(events, Exception):
                    self.logger.error(f"Error scraping {name}: {events}")
                    continue

                events_by_book[name] = events
                self.logger.info(f"Scraped {len(events)} events from {name}")

            # Aggregate events
            aggregated = self._aggregate_events(events_by_book, s)
            results[s] = aggregated

            self.logger.info(f"Aggregated {len(aggregated)} unique {s} events")

        return results

    def _aggregate_events(
        self,
        events_by_book: Dict[str, List[ScrapedEvent]],
        sport: str
    ) -> List[AggregatedEvent]:
        """
        Match and aggregate events from different bookmakers.
        """
        aggregated = []
        matched_events = set()  # Track already matched events

        # Start with events from each bookmaker
        all_events = []
        for book_name, events in events_by_book.items():
            for event in events:
                all_events.append((book_name, event))

        # Group similar events
        for i, (book1, event1) in enumerate(all_events):
            if i in matched_events:
                continue

            # Create aggregated event
            agg_event = AggregatedEvent(
                sport=sport,
                league=event1.league,
                home_team=event1.home_team,
                away_team=event1.away_team,
                start_time=event1.start_time,
                bookmaker_odds={event1.bookmaker: event1.odds}
            )

            matched_events.add(i)

            # Find matching events from other bookmakers
            for j, (book2, event2) in enumerate(all_events):
                if j in matched_events:
                    continue

                if book2 == book1:
                    continue

                if self._events_match(event1, event2):
                    # Add odds from this bookmaker
                    agg_event.bookmaker_odds[event2.bookmaker] = event2.odds

                    # Use better league name if available
                    if event2.league and not agg_event.league:
                        agg_event.league = event2.league

                    matched_events.add(j)

            aggregated.append(agg_event)

        return aggregated

    def _events_match(self, event1: ScrapedEvent, event2: ScrapedEvent) -> bool:
        """
        Determine if two events represent the same match.
        """
        # Check time proximity
        time_diff = abs((event1.start_time - event2.start_time).total_seconds())
        if time_diff > self.time_window_minutes * 60:
            return False

        # Check team similarity
        home_sim = self._team_similarity(event1.home_team, event2.home_team)
        away_sim = self._team_similarity(event1.away_team, event2.away_team)

        if home_sim >= self.team_match_threshold and away_sim >= self.team_match_threshold:
            return True

        # Check if teams are swapped (different home/away designation)
        home_away_sim = self._team_similarity(event1.home_team, event2.away_team)
        away_home_sim = self._team_similarity(event1.away_team, event2.home_team)

        if home_away_sim >= self.team_match_threshold and away_home_sim >= self.team_match_threshold:
            return True

        return False

    def _team_similarity(self, team1: str, team2: str) -> float:
        """
        Calculate similarity between team names.
        """
        # Normalize names
        t1 = self._normalize_team_name(team1)
        t2 = self._normalize_team_name(team2)

        # Exact match
        if t1 == t2:
            return 1.0

        # Check if one is substring of other
        if t1 in t2 or t2 in t1:
            return 0.9

        # Use sequence matcher
        return SequenceMatcher(None, t1, t2).ratio()

    def _normalize_team_name(self, name: str) -> str:
        """
        Normalize team name for comparison.
        """
        # Lowercase
        normalized = name.lower()

        # Remove common prefixes/suffixes
        removes = [
            'fc', 'fk', 'sk', 'hc', 'ac', 'as', 'sc', 'cf', 'cd',
            'real', 'dynamo', 'sporting', 'athletic', 'atletico',
            'united', 'city', 'town', 'rovers', 'wanderers'
        ]

        for term in removes:
            normalized = normalized.replace(f' {term} ', ' ')
            normalized = normalized.replace(f' {term}', '')
            normalized = normalized.replace(f'{term} ', '')

        # Remove special characters
        normalized = ''.join(c for c in normalized if c.isalnum() or c.isspace())

        # Remove extra spaces
        normalized = ' '.join(normalized.split())

        return normalized.strip()

    async def scrape_single_sport(self, sport: str) -> List[AggregatedEvent]:
        """Convenience method to scrape a single sport."""
        results = await self.scrape_all(sport)
        return results.get(sport, [])

    def get_events_with_sharp_odds(self, events: List[AggregatedEvent]) -> List[AggregatedEvent]:
        """Filter events that have sharp bookmaker odds."""
        return [e for e in events if e.has_sharp_odds()]

    def get_events_by_league(
        self,
        events: List[AggregatedEvent],
        leagues: List[str]
    ) -> List[AggregatedEvent]:
        """Filter events by league names."""
        filtered = []

        for event in events:
            for league in leagues:
                if league.lower() in event.league.lower():
                    filtered.append(event)
                    break

        return filtered


async def main():
    """Test the odds aggregator."""
    import logging
    logging.basicConfig(level=logging.INFO)

    aggregator = OddsAggregator()

    # Scrape football
    events = await aggregator.scrape_single_sport('football')

    print(f"\nFound {len(events)} football events\n")

    for event in events[:5]:
        print(f"{event.home_team} vs {event.away_team}")
        print(f"  Start: {event.start_time}")
        print(f"  Books: {list(event.bookmaker_odds.keys())}")

        best = event.get_best_odds()
        print(f"  Best odds:")
        for sel, (odds, book) in best.items():
            print(f"    {sel}: {odds} ({book})")
        print()


if __name__ == "__main__":
    asyncio.run(main())
