"""
Pinnacle Scraper
================

Scraper for Pinnacle - Sharp international bookmaker.
This is the gold standard for true odds.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json

from .base_scraper import BaseScraper, ScrapedEvent, SeleniumScraperMixin


class PinnacleScraper(BaseScraper, SeleniumScraperMixin):
    """
    Scraper for Pinnacle.

    Pinnacle is a sharp bookmaker with the lowest margins in the industry.
    Used as the baseline for true probability calculations.

    Note: Requires VPN access from some countries.
    """

    def __init__(self, config: dict = None):
        BaseScraper.__init__(self, config)
        SeleniumScraperMixin.__init__(self)

        self.name = "Pinnacle"
        self.base_url = "https://www.pinnacle.com"

        # Pinnacle's API is more restricted, may need web scraping
        self.sport_ids = {
            'football': 29,  # Soccer
            'hockey': 19,    # Hockey
            'tennis': 33,    # Tennis
        }

        # Headers for Pinnacle
        self.headers.update({
            'Referer': 'https://www.pinnacle.com/',
            'Origin': 'https://www.pinnacle.com',
        })

    async def _fetch_sport_data(self, sport: str) -> List[ScrapedEvent]:
        """Fetch sport data from Pinnacle."""
        sport_id = self.sport_ids.get(sport)
        if not sport_id:
            return []

        # Try various API patterns
        endpoints = [
            f"https://guest.api.arcadia.pinnacle.com/0.1/sports/{sport_id}/matchups",
            f"https://www.pinnacle.com/api/sports/{sport_id}/events",
        ]

        for endpoint in endpoints:
            data = await self.fetch_json(endpoint)
            if data:
                return self._parse_api_response(data, sport)

        # Try web scraping with Playwright
        try:
            return await self._scrape_with_browser(sport)
        except Exception as e:
            self.logger.error(f"Browser scraping failed: {e}")

        return []

    def _parse_api_response(self, data: dict, sport: str) -> List[ScrapedEvent]:
        """Parse Pinnacle API response."""
        events = []

        # Handle different response formats
        if isinstance(data, list):
            matchups = data
        else:
            matchups = data.get('matchups', data.get('events', []))

        for matchup in matchups:
            event = self._parse_matchup(matchup, sport)
            if event:
                events.append(event)

        return events

    def _parse_matchup(self, data: dict, sport: str) -> Optional[ScrapedEvent]:
        """Parse single Pinnacle matchup."""
        try:
            # Get participants
            participants = data.get('participants', [])
            if len(participants) < 2:
                return None

            home = None
            away = None

            for p in participants:
                if p.get('alignment') == 'home':
                    home = p.get('name', '')
                elif p.get('alignment') == 'away':
                    away = p.get('name', '')

            if not home or not away:
                # Fallback to order
                home = participants[0].get('name', '')
                away = participants[1].get('name', '')

            if not home or not away:
                return None

            # Get league
            league = data.get('league', {}).get('name', '')

            # Get start time
            start_time = data.get('startTime', '')
            if isinstance(start_time, str):
                start_time = self.parse_datetime(start_time)
            elif isinstance(start_time, int):
                start_time = datetime.fromtimestamp(start_time / 1000)

            if not start_time:
                start_time = datetime.now() + timedelta(hours=1)

            # Get odds from prices
            odds = self._extract_pinnacle_odds(data)

            if not odds:
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
            self.logger.debug(f"Error parsing Pinnacle matchup: {e}")
            return None

    def _extract_pinnacle_odds(self, data: dict) -> Dict[str, Dict[str, float]]:
        """Extract odds from Pinnacle matchup data."""
        odds = {}

        # Pinnacle structure: prices array with different periods/markets
        prices = data.get('prices', [])

        for price in prices:
            market_key = price.get('marketKey', '')

            # Moneyline
            if market_key == 's;0;m' or 'moneyline' in market_key.lower():
                if 'moneyline' not in odds:
                    odds['moneyline'] = {}

                selections = price.get('selections', price.get('prices', []))
                for sel in selections:
                    designation = sel.get('designation', '')
                    value = sel.get('price', 0)

                    if value and float(value) > 1:
                        if designation == 'home':
                            odds['moneyline']['home'] = float(value)
                        elif designation == 'away':
                            odds['moneyline']['away'] = float(value)
                        elif designation == 'draw':
                            odds['moneyline']['draw'] = float(value)

            # Spread/handicap
            elif 'spread' in market_key.lower() or 'handicap' in market_key.lower():
                if 'spread' not in odds:
                    odds['spread'] = {}

                # Extract spread odds
                pass  # Add specific parsing if needed

            # Totals
            elif 'total' in market_key.lower():
                if 'total' not in odds:
                    odds['total'] = {}

                # Extract over/under
                pass  # Add specific parsing if needed

        # Fallback to direct odds fields
        if not odds.get('moneyline'):
            odds['moneyline'] = {}

            # Try different field names
            for field in ['homePrice', 'home_price', 'price_home']:
                if field in data:
                    odds['moneyline']['home'] = float(data[field])
                    break

            for field in ['awayPrice', 'away_price', 'price_away']:
                if field in data:
                    odds['moneyline']['away'] = float(data[field])
                    break

            for field in ['drawPrice', 'draw_price', 'price_draw']:
                if field in data:
                    odds['moneyline']['draw'] = float(data[field])
                    break

        return odds if odds.get('moneyline') else {}

    async def _scrape_with_browser(self, sport: str) -> List[ScrapedEvent]:
        """Scrape Pinnacle using headless browser."""
        sport_urls = {
            'football': f"{self.base_url}/en/soccer",
            'hockey': f"{self.base_url}/en/hockey",
            'tennis': f"{self.base_url}/en/tennis",
        }

        url = sport_urls.get(sport)
        if not url:
            return []

        try:
            content = await self.get_page_content(url, wait_selector='.market-btn')
            return self._parse_browser_content(content, sport)
        except Exception as e:
            self.logger.error(f"Browser scraping error: {e}")
            return []
        finally:
            await self.close_browser()

    def _parse_browser_content(self, html: str, sport: str) -> List[ScrapedEvent]:
        """Parse browser-rendered content."""
        from bs4 import BeautifulSoup
        import re

        soup = BeautifulSoup(html, 'lxml')
        events = []

        # Find event containers
        event_containers = soup.find_all('div', class_=re.compile(r'event|matchup|row'))

        for container in event_containers:
            try:
                # Find teams
                teams = container.find_all('span', class_=re.compile(r'participant|team'))
                if len(teams) < 2:
                    continue

                home = teams[0].get_text(strip=True)
                away = teams[1].get_text(strip=True)

                # Find odds buttons
                odds_buttons = container.find_all(['button', 'span'], class_=re.compile(r'market|price|odds'))

                odds = {'moneyline': {}}

                if len(odds_buttons) >= 3:
                    odds['moneyline']['home'] = self.parse_odds(odds_buttons[0].get_text())
                    odds['moneyline']['draw'] = self.parse_odds(odds_buttons[1].get_text())
                    odds['moneyline']['away'] = self.parse_odds(odds_buttons[2].get_text())
                elif len(odds_buttons) >= 2:
                    odds['moneyline']['home'] = self.parse_odds(odds_buttons[0].get_text())
                    odds['moneyline']['away'] = self.parse_odds(odds_buttons[1].get_text())

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
                self.logger.debug(f"Error parsing browser event: {e}")

        return events

    async def scrape_football(self) -> List[ScrapedEvent]:
        self.logger.info("Scraping Pinnacle football (sharp odds)...")
        return await self._fetch_sport_data('football')

    async def scrape_hockey(self) -> List[ScrapedEvent]:
        self.logger.info("Scraping Pinnacle hockey (sharp odds)...")
        return await self._fetch_sport_data('hockey')

    async def scrape_tennis(self) -> List[ScrapedEvent]:
        self.logger.info("Scraping Pinnacle tennis (sharp odds)...")
        return await self._fetch_sport_data('tennis')
