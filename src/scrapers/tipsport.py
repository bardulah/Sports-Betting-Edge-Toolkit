"""
Tipsport Scraper
================

Scraper for Tipsport.sk - Slovak bookmaker.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import re

from .base_scraper import BaseScraper, ScrapedEvent, ScrapedOdds


class TipsportScraper(BaseScraper):
    """
    Scraper for Tipsport Slovakia.

    Tipsport uses a REST API that returns JSON data.
    """

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.name = "Tipsport"
        self.base_url = "https://www.tipsport.sk"
        self.api_url = "https://www.tipsport.sk/rest"

        # Sport IDs on Tipsport
        self.sport_ids = {
            'football': 1,
            'hockey': 2,
            'tennis': 3,
            'basketball': 4,
        }

        # League mappings (Slovak focus)
        self.priority_leagues = {
            'football': [
                'Slovenská Fortuna liga',
                'Česká Fortuna liga',
                'Premier League',
                'La Liga',
                'Bundesliga',
                'Serie A',
                'Ligue 1',
                'Liga majstrov',
                'Európska liga'
            ],
            'hockey': [
                'Tipos Extraliga',
                'Česká extraliga',
                'NHL',
                'KHL'
            ],
            'tennis': [
                'ATP',
                'WTA'
            ]
        }

    async def _fetch_sport_data(self, sport: str) -> Optional[dict]:
        """Fetch sport data from API."""
        sport_id = self.sport_ids.get(sport)
        if not sport_id:
            return None

        # Try different API endpoints
        endpoints = [
            f"{self.api_url}/offer/v1/sportsMenu/{sport_id}",
            f"{self.api_url}/offer/v2/sports/{sport_id}/events",
            f"{self.api_url}/offer/v1/sports/{sport_id}/matches"
        ]

        for endpoint in endpoints:
            data = await self.fetch_json(endpoint)
            if data:
                return data

        # Fallback to HTML scraping
        return await self._scrape_html(sport)

    async def _scrape_html(self, sport: str) -> Optional[dict]:
        """Fallback HTML scraping."""
        sport_urls = {
            'football': f"{self.base_url}/kurzy/futbal",
            'hockey': f"{self.base_url}/kurzy/hokej",
            'tennis': f"{self.base_url}/kurzy/tenis"
        }

        url = sport_urls.get(sport)
        if not url:
            return None

        html = self.fetch_with_cloudscraper(url)
        if not html:
            return None

        return self._parse_html_events(html, sport)

    def _parse_html_events(self, html: str, sport: str) -> dict:
        """Parse events from HTML page."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'lxml')
        events = []

        # Find match rows (adjust selectors based on actual page structure)
        match_rows = soup.find_all('div', class_=re.compile(r'match|event|row'))

        for row in match_rows:
            try:
                # Extract team names
                teams = row.find_all('span', class_=re.compile(r'team|name|participant'))
                if len(teams) >= 2:
                    home_team = teams[0].get_text(strip=True)
                    away_team = teams[1].get_text(strip=True)
                else:
                    continue

                # Extract time
                time_elem = row.find('span', class_=re.compile(r'time|date'))
                start_time = None
                if time_elem:
                    time_text = time_elem.get_text(strip=True)
                    start_time = self.parse_datetime(time_text)

                if not start_time:
                    start_time = datetime.now() + timedelta(hours=1)

                # Extract odds
                odds_elems = row.find_all('span', class_=re.compile(r'odd|rate|kurz'))
                odds = {}

                if len(odds_elems) >= 3:
                    odds['1'] = self.parse_odds(odds_elems[0].get_text())
                    odds['X'] = self.parse_odds(odds_elems[1].get_text())
                    odds['2'] = self.parse_odds(odds_elems[2].get_text())
                elif len(odds_elems) >= 2:
                    odds['1'] = self.parse_odds(odds_elems[0].get_text())
                    odds['2'] = self.parse_odds(odds_elems[1].get_text())

                # Filter out invalid odds
                odds = {k: v for k, v in odds.items() if v and v > 1}

                if odds:
                    events.append({
                        'home_team': home_team,
                        'away_team': away_team,
                        'start_time': start_time,
                        'odds': {'moneyline': odds}
                    })

            except Exception as e:
                self.logger.debug(f"Error parsing row: {e}")
                continue

        return {'events': events, 'sport': sport}

    def _parse_api_events(self, data: dict, sport: str) -> List[ScrapedEvent]:
        """Parse events from API response."""
        events = []

        # Handle different API response formats
        event_list = data.get('events', data.get('matches', data.get('data', [])))

        if isinstance(event_list, dict):
            event_list = event_list.get('events', [])

        for event_data in event_list:
            try:
                event = self._parse_single_event(event_data, sport)
                if event:
                    events.append(event)
            except Exception as e:
                self.logger.debug(f"Error parsing event: {e}")
                continue

        return events

    def _parse_single_event(self, data: dict, sport: str) -> Optional[ScrapedEvent]:
        """Parse a single event from API data."""
        try:
            # Extract teams
            home_team = data.get('homeTeam', data.get('home', {}).get('name', ''))
            away_team = data.get('awayTeam', data.get('away', {}).get('name', ''))

            if not home_team or not away_team:
                participants = data.get('participants', [])
                if len(participants) >= 2:
                    home_team = participants[0].get('name', '')
                    away_team = participants[1].get('name', '')

            if not home_team or not away_team:
                return None

            # Extract league
            league = data.get('league', data.get('competition', {}).get('name', ''))
            if isinstance(league, dict):
                league = league.get('name', '')

            # Extract start time
            start_time_str = data.get('startTime', data.get('date', data.get('matchDate', '')))
            if isinstance(start_time_str, int):
                start_time = datetime.fromtimestamp(start_time_str / 1000)
            else:
                start_time = self.parse_datetime(str(start_time_str))

            if not start_time:
                return None

            # Extract odds
            odds = self._extract_odds(data)

            if not odds:
                return None

            return ScrapedEvent(
                bookmaker=self.name,
                external_id=str(data.get('id', data.get('matchId', ''))),
                sport=sport,
                league=league,
                home_team=home_team,
                away_team=away_team,
                start_time=start_time,
                is_live=data.get('isLive', False),
                odds=odds
            )

        except Exception as e:
            self.logger.debug(f"Error in _parse_single_event: {e}")
            return None

    def _extract_odds(self, data: dict) -> Dict[str, Dict[str, float]]:
        """Extract odds from event data."""
        odds = {}

        # Try different structures
        markets = data.get('markets', data.get('odds', data.get('rates', [])))

        if isinstance(markets, list):
            for market in markets:
                market_type = market.get('type', market.get('name', 'moneyline'))
                selections = market.get('selections', market.get('outcomes', []))

                market_odds = {}
                for sel in selections:
                    sel_name = sel.get('name', sel.get('outcome', ''))
                    sel_odds = sel.get('odds', sel.get('rate', sel.get('value', 0)))

                    if sel_odds and float(sel_odds) > 1:
                        market_odds[sel_name] = float(sel_odds)

                if market_odds:
                    odds[market_type] = market_odds

        elif isinstance(markets, dict):
            # Direct odds structure
            for key in ['1', 'X', '2', 'home', 'draw', 'away']:
                if key in markets:
                    if 'moneyline' not in odds:
                        odds['moneyline'] = {}

                    # Map to standard names
                    mapped_key = {
                        '1': 'home', 'home': 'home',
                        'X': 'draw', 'draw': 'draw',
                        '2': 'away', 'away': 'away'
                    }.get(key, key)

                    odds['moneyline'][mapped_key] = float(markets[key])

        # Also check direct odds fields
        if not odds:
            odds = {'moneyline': {}}

            for field, mapped in [('odds1', 'home'), ('oddsX', 'draw'), ('odds2', 'away'),
                                   ('home_odds', 'home'), ('draw_odds', 'draw'), ('away_odds', 'away')]:
                if field in data and data[field]:
                    odds['moneyline'][mapped] = float(data[field])

            if not odds['moneyline']:
                return {}

        return odds

    async def scrape_football(self) -> List[ScrapedEvent]:
        """Scrape football odds from Tipsport."""
        self.logger.info("Scraping Tipsport football...")

        data = await self._fetch_sport_data('football')
        if not data:
            self.logger.warning("No football data retrieved from Tipsport")
            return []

        if 'events' in data:
            # HTML scraping result
            events = []
            for event_data in data['events']:
                event = ScrapedEvent(
                    bookmaker=self.name,
                    external_id='',
                    sport='football',
                    league='',
                    home_team=event_data['home_team'],
                    away_team=event_data['away_team'],
                    start_time=event_data['start_time'],
                    odds=event_data['odds']
                )
                events.append(event)
            return events

        return self._parse_api_events(data, 'football')

    async def scrape_hockey(self) -> List[ScrapedEvent]:
        """Scrape hockey odds from Tipsport."""
        self.logger.info("Scraping Tipsport hockey...")

        data = await self._fetch_sport_data('hockey')
        if not data:
            self.logger.warning("No hockey data retrieved from Tipsport")
            return []

        if 'events' in data:
            events = []
            for event_data in data['events']:
                event = ScrapedEvent(
                    bookmaker=self.name,
                    external_id='',
                    sport='hockey',
                    league='',
                    home_team=event_data['home_team'],
                    away_team=event_data['away_team'],
                    start_time=event_data['start_time'],
                    odds=event_data['odds']
                )
                events.append(event)
            return events

        return self._parse_api_events(data, 'hockey')

    async def scrape_tennis(self) -> List[ScrapedEvent]:
        """Scrape tennis odds from Tipsport."""
        self.logger.info("Scraping Tipsport tennis...")

        data = await self._fetch_sport_data('tennis')
        if not data:
            self.logger.warning("No tennis data retrieved from Tipsport")
            return []

        if 'events' in data:
            events = []
            for event_data in data['events']:
                event = ScrapedEvent(
                    bookmaker=self.name,
                    external_id='',
                    sport='tennis',
                    league='',
                    home_team=event_data['home_team'],
                    away_team=event_data['away_team'],
                    start_time=event_data['start_time'],
                    odds=event_data['odds']
                )
                events.append(event)
            return events

        return self._parse_api_events(data, 'tennis')

    async def scrape_live(self) -> List[ScrapedEvent]:
        """Scrape live/in-play odds."""
        self.logger.info("Scraping Tipsport live...")

        live_url = f"{self.api_url}/offer/v1/live"
        data = await self.fetch_json(live_url)

        if not data:
            return []

        events = []
        for sport_data in data.get('sports', []):
            sport = sport_data.get('name', '').lower()
            if sport in ['futbal', 'football']:
                sport = 'football'
            elif sport in ['hokej', 'hockey']:
                sport = 'hockey'
            elif sport in ['tenis', 'tennis']:
                sport = 'tennis'
            else:
                continue

            for event_data in sport_data.get('events', []):
                event = self._parse_single_event(event_data, sport)
                if event:
                    event.is_live = True
                    events.append(event)

        return events
