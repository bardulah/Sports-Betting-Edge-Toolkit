"""
DOXXbet Scraper
===============

Scraper for DOXXbet.sk - Slovak bookmaker.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import re

from .base_scraper import BaseScraper, ScrapedEvent


class DoxxbetScraper(BaseScraper):
    """
    Scraper for DOXXbet Slovakia.
    """

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.name = "DOXXbet"
        self.base_url = "https://www.doxxbet.sk"
        self.api_url = "https://www.doxxbet.sk/api"

        self.sport_paths = {
            'football': 'futbal',
            'hockey': 'hokej',
            'tennis': 'tenis',
        }

    async def _fetch_sport_data(self, sport: str) -> List[ScrapedEvent]:
        """Fetch sport data from DOXXbet."""
        sport_path = self.sport_paths.get(sport)
        if not sport_path:
            return []

        # Try API
        endpoints = [
            f"{self.api_url}/offer/{sport_path}/events",
            f"{self.api_url}/betting/{sport_path}",
        ]

        for endpoint in endpoints:
            data = await self.fetch_json(endpoint)
            if data:
                return self._parse_api_response(data, sport)

        # Fallback HTML
        html = self.fetch_with_cloudscraper(f"{self.base_url}/tipovanie/{sport_path}")
        if html:
            return self._parse_html(html, sport)

        return []

    def _parse_api_response(self, data: dict, sport: str) -> List[ScrapedEvent]:
        """Parse API response."""
        events = []
        event_list = data.get('events', data.get('matches', []))

        for event_data in event_list:
            event = self._parse_event(event_data, sport)
            if event:
                events.append(event)

        return events

    def _parse_event(self, data: dict, sport: str) -> Optional[ScrapedEvent]:
        """Parse single event."""
        try:
            home = data.get('homeTeam', data.get('home', ''))
            away = data.get('awayTeam', data.get('away', ''))

            if isinstance(home, dict):
                home = home.get('name', '')
            if isinstance(away, dict):
                away = away.get('name', '')

            if not home or not away:
                return None

            league = data.get('competition', data.get('league', ''))
            if isinstance(league, dict):
                league = league.get('name', '')

            start_time = data.get('startTime', data.get('date', ''))
            if isinstance(start_time, int):
                start_time = datetime.fromtimestamp(start_time / 1000)
            elif isinstance(start_time, str):
                start_time = self.parse_datetime(start_time)

            if not start_time:
                start_time = datetime.now() + timedelta(hours=1)

            # Extract odds
            odds = {'moneyline': {}}

            markets = data.get('markets', data.get('odds', []))
            if isinstance(markets, list):
                for market in markets:
                    if market.get('type', '') in ['1X2', 'moneyline', '12']:
                        for sel in market.get('selections', []):
                            name = sel.get('name', '')
                            value = sel.get('odds', 0)

                            if name in ['1', 'home']:
                                odds['moneyline']['home'] = float(value)
                            elif name in ['X', 'draw']:
                                odds['moneyline']['draw'] = float(value)
                            elif name in ['2', 'away']:
                                odds['moneyline']['away'] = float(value)

            # Direct odds
            if not odds['moneyline']:
                for key, mapped in [('o1', 'home'), ('oX', 'draw'), ('o2', 'away')]:
                    if key in data and data[key]:
                        odds['moneyline'][mapped] = float(data[key])

            if not odds['moneyline']:
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
            self.logger.debug(f"Error parsing DOXXbet event: {e}")
            return None

    def _parse_html(self, html: str, sport: str) -> List[ScrapedEvent]:
        """Parse HTML page."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'lxml')
        events = []

        for elem in soup.find_all(['div', 'tr'], class_=re.compile(r'event|match')):
            try:
                teams = elem.find_all(class_=re.compile(r'team|name'))
                if len(teams) < 2:
                    continue

                home = teams[0].get_text(strip=True)
                away = teams[1].get_text(strip=True)

                odds_elems = elem.find_all(class_=re.compile(r'odd|rate'))
                if len(odds_elems) < 2:
                    continue

                odds = {'moneyline': {}}
                if len(odds_elems) >= 3:
                    odds['moneyline']['home'] = self.parse_odds(odds_elems[0].get_text())
                    odds['moneyline']['draw'] = self.parse_odds(odds_elems[1].get_text())
                    odds['moneyline']['away'] = self.parse_odds(odds_elems[2].get_text())
                else:
                    odds['moneyline']['home'] = self.parse_odds(odds_elems[0].get_text())
                    odds['moneyline']['away'] = self.parse_odds(odds_elems[1].get_text())

                odds['moneyline'] = {k: v for k, v in odds['moneyline'].items() if v and v > 1}

                if odds['moneyline']:
                    events.append(ScrapedEvent(
                        bookmaker=self.name,
                        external_id='',
                        sport=sport,
                        league='',
                        home_team=home,
                        away_team=away,
                        start_time=datetime.now() + timedelta(hours=1),
                        odds=odds
                    ))

            except Exception as e:
                self.logger.debug(f"Error parsing HTML: {e}")

        return events

    async def scrape_football(self) -> List[ScrapedEvent]:
        self.logger.info("Scraping DOXXbet football...")
        return await self._fetch_sport_data('football')

    async def scrape_hockey(self) -> List[ScrapedEvent]:
        self.logger.info("Scraping DOXXbet hockey...")
        return await self._fetch_sport_data('hockey')

    async def scrape_tennis(self) -> List[ScrapedEvent]:
        self.logger.info("Scraping DOXXbet tennis...")
        return await self._fetch_sport_data('tennis')
