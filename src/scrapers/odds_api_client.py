"""
The Odds API Client
===================

Production-ready integration with The Odds API (theoddsapi.com)
This is the primary source for Pinnacle and international books.

API Docs: https://the-odds-api.com/liveapi/guides/v4/
"""

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
import os

logger = logging.getLogger(__name__)


@dataclass
class OddsAPIEvent:
    """Event from The Odds API - canonical source of truth."""
    id: str  # Canonical event ID
    sport_key: str
    sport_title: str
    commence_time: datetime
    home_team: str
    away_team: str
    bookmakers: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class OddsAPIPrice:
    """Single odds price from The Odds API."""
    event_id: str
    bookmaker_key: str
    bookmaker_title: str
    market_key: str
    outcome_name: str
    price: float
    point: Optional[float] = None  # For spreads/totals
    last_update: datetime = None


class TheOddsAPIClient:
    """
    Client for The Odds API.

    Pricing (as of 2024):
    - Free: 500 requests/month
    - Starter: $20/mo for 10,000 requests
    - Standard: $50/mo for 50,000 requests

    One request = one sport + one region + one market
    """

    BASE_URL = "https://api.the-odds-api.com/v4"

    # Sport keys for our focus areas
    SPORT_KEYS = {
        'football': 'soccer',  # Generic soccer
        'soccer_epl': 'soccer_epl',  # Premier League
        'soccer_spain_la_liga': 'soccer_spain_la_liga',
        'soccer_germany_bundesliga': 'soccer_germany_bundesliga',
        'soccer_italy_serie_a': 'soccer_italy_serie_a',
        'soccer_france_ligue_one': 'soccer_france_ligue_one',
        'soccer_uefa_champs_league': 'soccer_uefa_champs_league',
        'soccer_uefa_europa_league': 'soccer_uefa_europa_league',
        'hockey_nhl': 'icehockey_nhl',
        'tennis_atp': 'tennis_atp_french_open',  # ATP events
        'tennis_wta': 'tennis_wta_french_open',
    }

    # Bookmaker keys - these are the ones we care about
    BOOKMAKER_KEYS = {
        'pinnacle': 'pinnacle',
        'bet365': 'bet365',
        'unibet': 'unibet',
        'betfair': 'betfair_ex_eu',
        'williamhill': 'williamhill',
        'betway': 'betway',
        '1xbet': 'onexbet',
        'marathon': 'marathonbet',
    }

    def __init__(self, api_key: str = None):
        """Initialize client with API key."""
        self.api_key = api_key or os.getenv('ODDS_API_KEY')

        if not self.api_key:
            raise ValueError(
                "The Odds API key required. Get one at https://the-odds-api.com/ "
                "Set ODDS_API_KEY env var or pass to constructor."
            )

        self.session: Optional[aiohttp.ClientSession] = None
        self.requests_remaining = None
        self.requests_used = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def close(self):
        """Close the session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def _request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make API request."""
        session = await self._get_session()

        params = params or {}
        params['apiKey'] = self.api_key

        url = f"{self.BASE_URL}/{endpoint}"

        try:
            async with session.get(url, params=params) as response:
                # Track API usage from headers
                self.requests_remaining = response.headers.get('x-requests-remaining')
                self.requests_used = response.headers.get('x-requests-used')

                if response.status == 200:
                    data = await response.json()
                    logger.debug(f"API request successful. Remaining: {self.requests_remaining}")
                    return data
                elif response.status == 401:
                    logger.error("Invalid API key")
                    return None
                elif response.status == 422:
                    error = await response.json()
                    logger.error(f"API error: {error.get('message', 'Unknown')}")
                    return None
                elif response.status == 429:
                    logger.error("Rate limited - out of requests")
                    return None
                else:
                    logger.error(f"API error: HTTP {response.status}")
                    return None

        except asyncio.TimeoutError:
            logger.error(f"Timeout requesting {endpoint}")
            return None
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None

    async def get_sports(self) -> List[dict]:
        """Get list of available sports."""
        return await self._request("sports") or []

    async def get_odds(
        self,
        sport_key: str,
        regions: str = "eu",
        markets: str = "h2h",
        odds_format: str = "decimal",
        bookmakers: List[str] = None
    ) -> List[OddsAPIEvent]:
        """
        Get odds for a sport.

        Args:
            sport_key: Sport identifier (e.g., 'soccer_epl')
            regions: Comma-separated regions (us, uk, eu, au)
            markets: Comma-separated markets (h2h, spreads, totals)
            odds_format: decimal or american
            bookmakers: Specific bookmakers to include

        Returns:
            List of events with odds
        """
        params = {
            'regions': regions,
            'markets': markets,
            'oddsFormat': odds_format,
        }

        if bookmakers:
            params['bookmakers'] = ','.join(bookmakers)

        data = await self._request(f"sports/{sport_key}/odds", params)

        if not data:
            return []

        events = []
        for event_data in data:
            try:
                event = OddsAPIEvent(
                    id=event_data['id'],
                    sport_key=event_data['sport_key'],
                    sport_title=event_data['sport_title'],
                    commence_time=datetime.fromisoformat(
                        event_data['commence_time'].replace('Z', '+00:00')
                    ),
                    home_team=event_data['home_team'],
                    away_team=event_data['away_team'],
                    bookmakers=event_data.get('bookmakers', [])
                )
                events.append(event)
            except Exception as e:
                logger.warning(f"Failed to parse event: {e}")
                continue

        logger.info(f"Retrieved {len(events)} events for {sport_key}")
        return events

    async def get_odds_for_event(
        self,
        sport_key: str,
        event_id: str,
        regions: str = "eu",
        markets: str = "h2h",
        odds_format: str = "decimal"
    ) -> Optional[OddsAPIEvent]:
        """Get odds for a specific event."""
        params = {
            'regions': regions,
            'markets': markets,
            'oddsFormat': odds_format,
        }

        data = await self._request(
            f"sports/{sport_key}/events/{event_id}/odds",
            params
        )

        if not data:
            return None

        return OddsAPIEvent(
            id=data['id'],
            sport_key=data['sport_key'],
            sport_title=data['sport_title'],
            commence_time=datetime.fromisoformat(
                data['commence_time'].replace('Z', '+00:00')
            ),
            home_team=data['home_team'],
            away_team=data['away_team'],
            bookmakers=data.get('bookmakers', [])
        )

    async def get_historical_odds(
        self,
        sport_key: str,
        event_id: str,
        date: datetime,
        regions: str = "eu",
        markets: str = "h2h",
        odds_format: str = "decimal"
    ) -> Optional[dict]:
        """
        Get historical odds (requires paid plan).

        Args:
            sport_key: Sport key
            event_id: Event ID
            date: Historical date to query
            regions: Region
            markets: Markets
            odds_format: Format
        """
        params = {
            'regions': regions,
            'markets': markets,
            'oddsFormat': odds_format,
            'date': date.isoformat(),
        }

        return await self._request(
            f"sports/{sport_key}/events/{event_id}/odds-history",
            params
        )

    async def get_all_football_odds(self) -> List[OddsAPIEvent]:
        """Get odds for all football/soccer leagues we care about."""
        all_events = []

        soccer_sports = [
            'soccer_epl',
            'soccer_spain_la_liga',
            'soccer_germany_bundesliga',
            'soccer_italy_serie_a',
            'soccer_france_ligue_one',
            'soccer_uefa_champs_league',
            'soccer_uefa_europa_league',
        ]

        for sport_key in soccer_sports:
            try:
                events = await self.get_odds(
                    sport_key,
                    regions='eu',
                    markets='h2h',
                    bookmakers=['pinnacle', 'bet365', 'unibet', 'betway']
                )
                all_events.extend(events)
                await asyncio.sleep(0.5)  # Rate limit courtesy
            except Exception as e:
                logger.error(f"Error fetching {sport_key}: {e}")
                continue

        return all_events

    async def get_all_hockey_odds(self) -> List[OddsAPIEvent]:
        """Get odds for hockey."""
        return await self.get_odds(
            'icehockey_nhl',
            regions='eu',
            markets='h2h',
            bookmakers=['pinnacle', 'bet365', 'unibet']
        )

    async def get_all_tennis_odds(self) -> List[OddsAPIEvent]:
        """Get odds for tennis - need to check available tournaments."""
        # Tennis tournaments rotate, so get available sports first
        sports = await self.get_sports()
        tennis_sports = [s['key'] for s in sports if 'tennis' in s['key'] and s['active']]

        all_events = []
        for sport_key in tennis_sports[:3]:  # Limit to avoid burning requests
            try:
                events = await self.get_odds(
                    sport_key,
                    regions='eu',
                    markets='h2h',
                    bookmakers=['pinnacle', 'bet365']
                )
                all_events.extend(events)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error fetching {sport_key}: {e}")

        return all_events

    def extract_prices(self, event: OddsAPIEvent) -> List[OddsAPIPrice]:
        """Extract all prices from an event into flat list."""
        prices = []

        for bookmaker in event.bookmakers:
            book_key = bookmaker['key']
            book_title = bookmaker['title']
            last_update = datetime.fromisoformat(
                bookmaker['last_update'].replace('Z', '+00:00')
            )

            for market in bookmaker.get('markets', []):
                market_key = market['key']

                for outcome in market.get('outcomes', []):
                    price = OddsAPIPrice(
                        event_id=event.id,
                        bookmaker_key=book_key,
                        bookmaker_title=book_title,
                        market_key=market_key,
                        outcome_name=outcome['name'],
                        price=outcome['price'],
                        point=outcome.get('point'),
                        last_update=last_update
                    )
                    prices.append(price)

        return prices

    def get_pinnacle_odds(self, event: OddsAPIEvent) -> Dict[str, float]:
        """Extract Pinnacle odds from event (our sharp baseline)."""
        for bookmaker in event.bookmakers:
            if bookmaker['key'] == 'pinnacle':
                odds = {}
                for market in bookmaker.get('markets', []):
                    if market['key'] == 'h2h':
                        for outcome in market['outcomes']:
                            name = outcome['name']
                            # Normalize to home/away/draw
                            if name == event.home_team:
                                odds['home'] = outcome['price']
                            elif name == event.away_team:
                                odds['away'] = outcome['price']
                            elif name.lower() == 'draw':
                                odds['draw'] = outcome['price']
                return odds
        return {}

    def get_best_odds(self, event: OddsAPIEvent) -> Dict[str, tuple]:
        """Get best odds for each outcome across all bookmakers."""
        best = {}  # {outcome: (odds, bookmaker)}

        for bookmaker in event.bookmakers:
            for market in bookmaker.get('markets', []):
                if market['key'] == 'h2h':
                    for outcome in market['outcomes']:
                        name = outcome['name']
                        price = outcome['price']

                        # Normalize name
                        if name == event.home_team:
                            key = 'home'
                        elif name == event.away_team:
                            key = 'away'
                        elif name.lower() == 'draw':
                            key = 'draw'
                        else:
                            key = name

                        if key not in best or price > best[key][0]:
                            best[key] = (price, bookmaker['title'])

        return best

    def get_api_usage(self) -> dict:
        """Get current API usage stats."""
        return {
            'requests_remaining': self.requests_remaining,
            'requests_used': self.requests_used
        }


# Convenience function
async def fetch_all_odds(api_key: str = None) -> Dict[str, List[OddsAPIEvent]]:
    """Fetch all odds from The Odds API."""
    client = TheOddsAPIClient(api_key)

    try:
        results = {
            'football': await client.get_all_football_odds(),
            'hockey': await client.get_all_hockey_odds(),
            'tennis': await client.get_all_tennis_odds(),
        }

        logger.info(f"API Usage: {client.get_api_usage()}")
        return results

    finally:
        await client.close()
