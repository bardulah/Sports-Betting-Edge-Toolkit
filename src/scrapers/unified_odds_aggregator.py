"""
Unified Odds Aggregator
=======================

Combines The Odds API (international/sharp books) with Slovak scraper
(local soft books) into a unified view with proper event matching.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from difflib import SequenceMatcher
import re

from .odds_api_client import TheOddsAPIClient, OddsAPIEvent
from .slovak_scraper_adapter import SlovakScraperAdapter, SlovakScrapedEvent
from ..database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class UnifiedEvent:
    """
    Event with odds from all sources.

    Uses The Odds API event ID as canonical identifier.
    """
    # Canonical ID from The Odds API
    canonical_id: str

    # Event info
    sport: str
    league: str
    home_team: str
    away_team: str
    start_time: datetime

    # Odds from all bookmakers
    # Format: {bookmaker_key: {market: {selection: odds}}}
    bookmaker_odds: Dict[str, Dict[str, Dict[str, float]]] = field(default_factory=dict)

    # Track which sources contributed
    sources: List[str] = field(default_factory=list)

    # Matched Slovak events (for reference)
    matched_slovak_events: Dict[str, str] = field(default_factory=dict)  # {bookmaker: external_id}

    def has_sharp_odds(self) -> bool:
        """Check if we have Pinnacle odds."""
        return 'pinnacle' in self.bookmaker_odds

    def get_pinnacle_odds(self, market: str = 'h2h') -> Optional[Dict[str, float]]:
        """Get Pinnacle odds for a market."""
        return self.bookmaker_odds.get('pinnacle', {}).get(market)

    def get_best_odds(self, market: str = 'h2h') -> Dict[str, Tuple[float, str]]:
        """Get best odds for each selection."""
        best = {}

        for bookmaker, markets in self.bookmaker_odds.items():
            if market not in markets:
                continue

            for selection, odds in markets[market].items():
                if selection not in best or odds > best[selection][0]:
                    best[selection] = (odds, bookmaker)

        return best

    def get_all_odds_for_selection(self, selection: str, market: str = 'h2h') -> List[Tuple[float, str]]:
        """Get all odds for a specific selection, sorted best first."""
        odds_list = []

        for bookmaker, markets in self.bookmaker_odds.items():
            if market in markets and selection in markets[market]:
                odds_list.append((markets[market][selection], bookmaker))

        return sorted(odds_list, key=lambda x: x[0], reverse=True)


class EventMatcher:
    """
    Matches events from different sources.

    Uses The Odds API events as canonical source of truth.
    Matches Slovak scraper events to these using fuzzy matching.
    """

    def __init__(self):
        # Team name normalization patterns
        self.remove_patterns = [
            r'\bFC\b', r'\bFK\b', r'\bSK\b', r'\bHC\b', r'\bAC\b',
            r'\bAS\b', r'\bSC\b', r'\bCF\b', r'\bCD\b', r'\bUnited\b',
            r'\bCity\b', r'\bReal\b', r'\bDynamo\b', r'\bSporting\b',
        ]

        # Slovak to English team name mappings
        self.team_mappings = {
            'šk slovan bratislava': 'slovan bratislava',
            'spartak trnava': 'trnava',
            'mšk žilina': 'zilina',
            'fc košice': 'kosice',
            'hk nitra': 'nitra',
            'hc košice': 'kosice',
            # Add more as needed
        }

        # League name mappings
        self.league_mappings = {
            'slovenská fortuna liga': 'slovakia super liga',
            'tipos extraliga': 'slovakia extraliga',
            'česká fortuna liga': 'czech first league',
        }

    def normalize_team_name(self, name: str) -> str:
        """Normalize team name for matching."""
        # Lowercase
        normalized = name.lower().strip()

        # Apply direct mappings first
        if normalized in self.team_mappings:
            normalized = self.team_mappings[normalized]

        # Remove common suffixes/prefixes
        for pattern in self.remove_patterns:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

        # Remove special characters, keep letters and spaces
        normalized = re.sub(r'[^\w\s]', '', normalized)

        # Collapse whitespace
        normalized = ' '.join(normalized.split())

        return normalized

    def calculate_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two team names."""
        n1 = self.normalize_team_name(name1)
        n2 = self.normalize_team_name(name2)

        # Exact match
        if n1 == n2:
            return 1.0

        # One contains the other
        if n1 in n2 or n2 in n1:
            return 0.9

        # Fuzzy match
        return SequenceMatcher(None, n1, n2).ratio()

    def match_events(
        self,
        canonical: OddsAPIEvent,
        slovak_events: List[SlovakScrapedEvent],
        time_window_minutes: int = 30,
        min_similarity: float = 0.7
    ) -> Optional[SlovakScrapedEvent]:
        """
        Find matching Slovak event for a canonical event.

        Args:
            canonical: Event from The Odds API
            slovak_events: List of events from Slovak scraper
            time_window_minutes: Maximum time difference
            min_similarity: Minimum team name similarity

        Returns:
            Best matching Slovak event or None
        """
        best_match = None
        best_score = 0

        for slovak_event in slovak_events:
            # Check time proximity
            time_diff = abs(
                (canonical.commence_time - slovak_event.start_time).total_seconds()
            )
            if time_diff > time_window_minutes * 60:
                continue

            # Calculate team similarity
            home_sim = self.calculate_similarity(
                canonical.home_team, slovak_event.home_team
            )
            away_sim = self.calculate_similarity(
                canonical.away_team, slovak_event.away_team
            )

            # Try both orderings (home/away might be swapped)
            score1 = (home_sim + away_sim) / 2
            score2 = (
                self.calculate_similarity(canonical.home_team, slovak_event.away_team) +
                self.calculate_similarity(canonical.away_team, slovak_event.home_team)
            ) / 2

            score = max(score1, score2)

            if score >= min_similarity and score > best_score:
                best_score = score
                best_match = slovak_event

        return best_match


class UnifiedOddsAggregator:
    """
    Main aggregator that combines all odds sources.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}

        # Initialize components
        api_key = self.config.get('odds_api_key')
        self.odds_api = TheOddsAPIClient(api_key) if api_key else None

        self.slovak_adapter = SlovakScraperAdapter(self.config)
        self.matcher = EventMatcher()

        # Database for storing historical odds
        self.db = DatabaseManager(self.config.get('database_path', 'data/betting_edge.db'))

    async def aggregate_all(self, sport: str = None) -> List[UnifiedEvent]:
        """
        Aggregate odds from all sources.

        Args:
            sport: Optional filter ('football', 'hockey', 'tennis')

        Returns:
            List of UnifiedEvent with odds from all bookmakers
        """
        unified_events = []

        # Step 1: Get canonical events from The Odds API
        if self.odds_api:
            api_events = await self._fetch_from_odds_api(sport)
            logger.info(f"Retrieved {len(api_events)} events from The Odds API")
        else:
            api_events = []
            logger.warning("The Odds API not configured - no sharp odds available!")

        # Step 2: Get Slovak bookmaker events
        slovak_events_by_book = await self.slovak_adapter.scrape_all(sport)

        total_slovak = sum(len(events) for events in slovak_events_by_book.values())
        logger.info(f"Scraped {total_slovak} events from Slovak bookmakers")

        # Step 3: Create unified events from API (canonical)
        for api_event in api_events:
            unified = UnifiedEvent(
                canonical_id=api_event.id,
                sport=self._normalize_sport(api_event.sport_key),
                league=api_event.sport_title,
                home_team=api_event.home_team,
                away_team=api_event.away_team,
                start_time=api_event.commence_time,
                sources=['odds_api']
            )

            # Add odds from API bookmakers
            for bookmaker in api_event.bookmakers:
                book_key = bookmaker['key']
                unified.bookmaker_odds[book_key] = {}

                for market in bookmaker.get('markets', []):
                    market_key = market['key']
                    unified.bookmaker_odds[book_key][market_key] = {}

                    for outcome in market['outcomes']:
                        # Normalize outcome name
                        name = outcome['name']
                        if name == api_event.home_team:
                            name = 'home'
                        elif name == api_event.away_team:
                            name = 'away'
                        elif name.lower() == 'draw':
                            name = 'draw'

                        unified.bookmaker_odds[book_key][market_key][name] = outcome['price']

            # Step 4: Match Slovak events and add their odds
            for book_name, slovak_events in slovak_events_by_book.items():
                matched = self.matcher.match_events(api_event, slovak_events)

                if matched:
                    unified.matched_slovak_events[book_name] = matched.external_id
                    unified.sources.append(book_name)

                    # Add Slovak odds (normalize to h2h)
                    unified.bookmaker_odds[book_name] = {}

                    if 'moneyline' in matched.odds:
                        unified.bookmaker_odds[book_name]['h2h'] = matched.odds['moneyline']
                    elif 'h2h' in matched.odds:
                        unified.bookmaker_odds[book_name]['h2h'] = matched.odds['h2h']

            unified_events.append(unified)

        # Step 5: Handle Slovak events that didn't match (Slovak leagues only)
        unmatched_slovak = self._collect_unmatched_slovak(
            api_events, slovak_events_by_book
        )

        for event in unmatched_slovak:
            unified = UnifiedEvent(
                canonical_id=f"slovak_{event.bookmaker}_{event.external_id}",
                sport=event.sport,
                league=event.league,
                home_team=event.home_team,
                away_team=event.away_team,
                start_time=event.start_time,
                sources=[event.bookmaker]
            )

            # Add odds
            unified.bookmaker_odds[event.bookmaker] = {}
            if 'moneyline' in event.odds:
                unified.bookmaker_odds[event.bookmaker]['h2h'] = event.odds['moneyline']

            unified_events.append(unified)

        # Step 6: Store historical odds
        await self._store_historical_odds(unified_events)

        logger.info(f"Aggregated {len(unified_events)} unified events")
        return unified_events

    async def _fetch_from_odds_api(self, sport: str = None) -> List[OddsAPIEvent]:
        """Fetch events from The Odds API."""
        events = []

        if sport is None or sport == 'football':
            events.extend(await self.odds_api.get_all_football_odds())

        if sport is None or sport == 'hockey':
            events.extend(await self.odds_api.get_all_hockey_odds())

        if sport is None or sport == 'tennis':
            events.extend(await self.odds_api.get_all_tennis_odds())

        return events

    def _normalize_sport(self, sport_key: str) -> str:
        """Normalize sport key to standard name."""
        if 'soccer' in sport_key:
            return 'football'
        elif 'hockey' in sport_key or 'icehockey' in sport_key:
            return 'hockey'
        elif 'tennis' in sport_key:
            return 'tennis'
        else:
            return sport_key

    def _collect_unmatched_slovak(
        self,
        api_events: List[OddsAPIEvent],
        slovak_by_book: Dict[str, List[SlovakScrapedEvent]]
    ) -> List[SlovakScrapedEvent]:
        """Collect Slovak events that didn't match any API event."""
        unmatched = []

        # Flatten all Slovak events
        all_slovak = []
        for events in slovak_by_book.values():
            all_slovak.extend(events)

        # Find unmatched
        for slovak_event in all_slovak:
            matched = False
            for api_event in api_events:
                if self.matcher.match_events(api_event, [slovak_event]):
                    matched = True
                    break

            if not matched:
                unmatched.append(slovak_event)

        logger.info(f"Found {len(unmatched)} unmatched Slovak events")
        return unmatched

    async def _store_historical_odds(self, events: List[UnifiedEvent]):
        """Store odds snapshot for historical tracking."""
        from ..database.models import OddsHistory

        timestamp = datetime.now()

        with self.db.get_session() as session:
            for event in events:
                # Get or create event in DB
                db_event = self.db.find_event(
                    event.home_team, event.away_team, event.start_time
                )

                if not db_event:
                    event_id = self.db.add_event({
                        'sport': event.sport,
                        'league': event.league,
                        'home_team': event.home_team,
                        'away_team': event.away_team,
                        'start_time': event.start_time,
                        'external_id': event.canonical_id
                    })
                else:
                    event_id = db_event.id

                # Store odds from each bookmaker
                for bookmaker, markets in event.bookmaker_odds.items():
                    for market_type, selections in markets.items():
                        for selection, odds_value in selections.items():
                            record = OddsHistory(
                                event_id=event_id,
                                bookmaker=bookmaker,
                                market_type=market_type,
                                selection=selection,
                                odds_value=odds_value,
                                timestamp=timestamp
                            )
                            session.add(record)

    async def get_events_with_sharp(self) -> List[UnifiedEvent]:
        """Get only events that have sharp (Pinnacle) odds."""
        events = await self.aggregate_all()
        return [e for e in events if e.has_sharp_odds()]

    async def get_events_by_sport(self, sport: str) -> List[UnifiedEvent]:
        """Get events for a specific sport."""
        return await self.aggregate_all(sport)

    async def close(self):
        """Clean up resources."""
        if self.odds_api:
            await self.odds_api.close()
        await self.slovak_adapter.close()

    def get_api_usage(self) -> dict:
        """Get The Odds API usage stats."""
        if self.odds_api:
            return self.odds_api.get_api_usage()
        return {}


# Convenience function
async def fetch_unified_odds(config: dict = None) -> List[UnifiedEvent]:
    """Fetch all unified odds."""
    aggregator = UnifiedOddsAggregator(config)

    try:
        return await aggregator.aggregate_all()
    finally:
        await aggregator.close()
