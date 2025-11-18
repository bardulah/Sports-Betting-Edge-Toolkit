"""
Fortuna Scraper
===============

Scraper for iFortuna.sk - Slovak bookmaker.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import re

from .base_scraper import BaseScraper, ScrapedEvent


class FortunaScraper(BaseScraper):
    """
    Scraper for Fortuna Slovakia.
    """

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.name = "Fortuna"
        self.base_url = "https://www.ifortuna.sk"
        self.api_url = "https://www.ifortuna.sk/api"

        # Sport paths
        self.sport_paths = {
            'football': '/futbal',
            'hockey': '/hokej',
            'tennis': '/tenis',
        }

    async def _fetch_sport_data(self, sport: str) -> List[ScrapedEvent]:
        """Fetch sport data from Fortuna."""
        path = self.sport_paths.get(sport, '')
        if not path:
            return []

        # Try API endpoint
        api_endpoints = [
            f"{self.api_url}/betting/v1/sports{path}/events",
            f"{self.api_url}/offer{path}",
        ]

        for endpoint in api_endpoints:
            data = await self.fetch_json(endpoint)
            if data:
                return self._parse_api_response(data, sport)

        # Fallback to HTML
        html = self.fetch_with_cloudscraper(f"{self.base_url}/tipovanie{path}")
        if html:
            return self._parse_html(html, sport)

        return []

    def _parse_api_response(self, data: dict, sport: str) -> List[ScrapedEvent]:
        """Parse API response."""
        events = []

        event_list = data.get('events', data.get('matches', data.get('items', [])))

        for event_data in event_list:
            try:
                event = self._parse_event(event_data, sport)
                if event:
                    events.append(event)
            except Exception as e:
                self.logger.debug(f"Error parsing Fortuna event: {e}")
                continue

        return events

    def _parse_event(self, data: dict, sport: str) -> Optional[ScrapedEvent]:
        """Parse single event."""
        try:
            # Get teams
            home = data.get('homeTeam', data.get('home', ''))
            away = data.get('awayTeam', data.get('away', ''))

            if isinstance(home, dict):
                home = home.get('name', '')
            if isinstance(away, dict):
                away = away.get('name', '')

            if not home or not away:
                return None

            # Get league
            league = data.get('competition', data.get('league', ''))
            if isinstance(league, dict):
                league = league.get('name', '')

            # Get time
            start_time = data.get('startTime', data.get('date', ''))
            if isinstance(start_time, int):
                start_time = datetime.fromtimestamp(start_time / 1000)
            elif isinstance(start_time, str):
                start_time = self.parse_datetime(start_time)

            if not start_time:
                start_time = datetime.now() + timedelta(hours=1)

            # Get odds
            odds = {}
            markets = data.get('markets', data.get('odds', []))

            if isinstance(markets, list):
                for market in markets:
                    mtype = market.get('type', 'moneyline')
                    selections = market.get('selections', market.get('outcomes', []))

                    market_odds = {}
                    for sel in selections:
                        name = sel.get('name', sel.get('outcome', ''))
                        value = sel.get('odds', sel.get('rate', 0))

                        if value and float(value) > 1:
                            # Normalize selection names
                            if name in ['1', home]:
                                name = 'home'
                            elif name in ['X', 'Remíza', 'Draw']:
                                name = 'draw'
                            elif name in ['2', away]:
                                name = 'away'

                            market_odds[name] = float(value)

                    if market_odds:
                        odds[mtype] = market_odds

            # Direct odds fields
            if not odds:
                odds = {'moneyline': {}}
                for key, mapped in [('odds1', 'home'), ('oddsX', 'draw'), ('odds2', 'away'),
                                     ('o1', 'home'), ('oX', 'draw'), ('o2', 'away')]:
                    if key in data and data[key]:
                        odds['moneyline'][mapped] = float(data[key])

            if not odds.get('moneyline'):
                return None

            return ScrapedEvent(
                bookmaker=self.name,
                external_id=str(data.get('id', '')),
                sport=sport,
                league=league,
                home_team=home,
                away_team=away,
                start_time=start_time,
                is_live=data.get('isLive', False),
                odds=odds
            )

        except Exception as e:
            self.logger.debug(f"Error in _parse_event: {e}")
            return None

    def _parse_html(self, html: str, sport: str) -> List[ScrapedEvent]:
        """Parse HTML page."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'lxml')
        events = []

        # Find event elements
        event_elements = soup.find_all(['div', 'tr'], class_=re.compile(r'event|match|row'))

        for elem in event_elements:
            try:
                # Find teams
                teams = elem.find_all(class_=re.compile(r'team|participant|name'))
                if len(teams) < 2:
                    continue

                home = teams[0].get_text(strip=True)
                away = teams[1].get_text(strip=True)

                # Find odds
                odds_elements = elem.find_all(class_=re.compile(r'odd|rate|kurz'))
                if len(odds_elements) < 2:
                    continue

                odds = {'moneyline': {}}
                if len(odds_elements) >= 3:
                    # 3-way (football)
                    odds['moneyline']['home'] = self.parse_odds(odds_elements[0].get_text())
                    odds['moneyline']['draw'] = self.parse_odds(odds_elements[1].get_text())
                    odds['moneyline']['away'] = self.parse_odds(odds_elements[2].get_text())
                else:
                    # 2-way (tennis/hockey)
                    odds['moneyline']['home'] = self.parse_odds(odds_elements[0].get_text())
                    odds['moneyline']['away'] = self.parse_odds(odds_elements[1].get_text())

                # Filter invalid odds
                odds['moneyline'] = {k: v for k, v in odds['moneyline'].items() if v and v > 1}

                if not odds['moneyline']:
                    continue

                # Time
                time_elem = elem.find(class_=re.compile(r'time|date'))
                start_time = datetime.now() + timedelta(hours=1)
                if time_elem:
                    parsed = self.parse_datetime(time_elem.get_text(strip=True))
                    if parsed:
                        start_time = parsed

                events.append(ScrapedEvent(
                    bookmaker=self.name,
                    external_id='',
                    sport=sport,
                    league='',
                    home_team=home,
                    away_team=away,
                    start_time=start_time,
                    odds=odds
                ))

            except Exception as e:
                self.logger.debug(f"Error parsing HTML event: {e}")
                continue

        return events

    async def scrape_football(self) -> List[ScrapedEvent]:
        """Scrape football odds."""
        self.logger.info("Scraping Fortuna football...")
        return await self._fetch_sport_data('football')

    async def scrape_hockey(self) -> List[ScrapedEvent]:
        """Scrape hockey odds."""
        self.logger.info("Scraping Fortuna hockey...")
        return await self._fetch_sport_data('hockey')

    async def scrape_tennis(self) -> List[ScrapedEvent]:
        """Scrape tennis odds."""
        self.logger.info("Scraping Fortuna tennis...")
        return await self._fetch_sport_data('tennis')
