"""
Bet365 Scraper
==============

Scraper for Bet365 - Major international bookmaker.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import re

from .base_scraper import BaseScraper, ScrapedEvent, SeleniumScraperMixin


class Bet365Scraper(BaseScraper, SeleniumScraperMixin):
    """
    Scraper for Bet365.

    Bet365 heavily protects against scraping, requires browser automation.
    """

    def __init__(self, config: dict = None):
        BaseScraper.__init__(self, config)
        SeleniumScraperMixin.__init__(self)

        self.name = "Bet365"
        self.base_url = "https://www.bet365.com"

        # Sport paths on Bet365
        self.sport_paths = {
            'football': '#/AC/B1/C1/D13/E51/F2/',
            'hockey': '#/AC/B17/C1/D50/E1/F50/',
            'tennis': '#/AC/B13/C1/D50/E1/F50/',
        }

    async def _fetch_sport_data(self, sport: str) -> List[ScrapedEvent]:
        """Fetch sport data from Bet365."""
        # Bet365 requires browser automation
        try:
            return await self._scrape_with_browser(sport)
        except Exception as e:
            self.logger.error(f"Bet365 scraping failed: {e}")
            return []

    async def _scrape_with_browser(self, sport: str) -> List[ScrapedEvent]:
        """Scrape Bet365 using headless browser."""
        sport_path = self.sport_paths.get(sport, '')
        url = f"{self.base_url}{sport_path}"

        try:
            # Initialize browser
            await self.init_playwright()

            page = await self.browser.new_page()

            # Set viewport and user agent
            await page.set_viewport_size({"width": 1920, "height": 1080})

            # Navigate
            await page.goto(url, wait_until='networkidle', timeout=30000)

            # Wait for content to load
            await asyncio.sleep(3)

            # Try to find and click "Accept cookies" if present
            try:
                accept_btn = await page.query_selector('button:has-text("Accept")')
                if accept_btn:
                    await accept_btn.click()
                    await asyncio.sleep(1)
            except:
                pass

            # Get page content
            content = await page.content()

            await page.close()

            return self._parse_browser_content(content, sport)

        except Exception as e:
            self.logger.error(f"Browser error: {e}")
            return []
        finally:
            await self.close_browser()

    def _parse_browser_content(self, html: str, sport: str) -> List[ScrapedEvent]:
        """Parse Bet365 page content."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'lxml')
        events = []

        # Bet365 has a complex structure, these selectors may need adjustment
        # Find participant containers
        participant_containers = soup.find_all('div', class_=re.compile(r'rcl-ParticipantFixtureDetails|gl-Participant'))

        if not participant_containers:
            # Try alternative structure
            event_rows = soup.find_all('div', class_=re.compile(r'sl-CouponFixtureLinkParticipant|cm-CouponMarketGroup'))
            return self._parse_event_rows(event_rows, sport)

        # Group into events (2 participants per event)
        i = 0
        while i < len(participant_containers) - 1:
            try:
                container1 = participant_containers[i]
                container2 = participant_containers[i + 1]

                # Get team names
                home = container1.get_text(strip=True)
                away = container2.get_text(strip=True)

                if not home or not away:
                    i += 1
                    continue

                # Find odds near these participants
                parent = container1.find_parent('div', class_=re.compile(r'gl-Market|rcl-MarketOddsButton'))

                odds = {'moneyline': {}}

                if parent:
                    odds_elements = parent.find_all('span', class_=re.compile(r'gl-MarketOdds|rcl-ParticipantOddsOnly'))

                    if len(odds_elements) >= 3:
                        odds['moneyline']['home'] = self.parse_odds(odds_elements[0].get_text())
                        odds['moneyline']['draw'] = self.parse_odds(odds_elements[1].get_text())
                        odds['moneyline']['away'] = self.parse_odds(odds_elements[2].get_text())
                    elif len(odds_elements) >= 2:
                        odds['moneyline']['home'] = self.parse_odds(odds_elements[0].get_text())
                        odds['moneyline']['away'] = self.parse_odds(odds_elements[1].get_text())

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

                i += 2

            except Exception as e:
                self.logger.debug(f"Error parsing Bet365 event: {e}")
                i += 1

        return events

    def _parse_event_rows(self, rows: list, sport: str) -> List[ScrapedEvent]:
        """Alternative parsing method."""
        events = []

        for row in rows:
            try:
                # Find team names
                teams = row.find_all(class_=re.compile(r'rcl-ParticipantFixtureDetailsTeam|team|participant'))
                if len(teams) < 2:
                    continue

                home = teams[0].get_text(strip=True)
                away = teams[1].get_text(strip=True)

                # Find odds
                odds_elements = row.find_all(class_=re.compile(r'gl-ParticipantOddsOnly|odds|price'))

                odds = {'moneyline': {}}

                if len(odds_elements) >= 3:
                    odds['moneyline']['home'] = self.parse_odds(odds_elements[0].get_text())
                    odds['moneyline']['draw'] = self.parse_odds(odds_elements[1].get_text())
                    odds['moneyline']['away'] = self.parse_odds(odds_elements[2].get_text())
                elif len(odds_elements) >= 2:
                    odds['moneyline']['home'] = self.parse_odds(odds_elements[0].get_text())
                    odds['moneyline']['away'] = self.parse_odds(odds_elements[1].get_text())

                odds['moneyline'] = {k: v for k, v in odds['moneyline'].items() if v and v > 1}

                if odds['moneyline'] and home and away:
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
                self.logger.debug(f"Error in _parse_event_rows: {e}")

        return events

    async def scrape_football(self) -> List[ScrapedEvent]:
        self.logger.info("Scraping Bet365 football...")
        return await self._fetch_sport_data('football')

    async def scrape_hockey(self) -> List[ScrapedEvent]:
        self.logger.info("Scraping Bet365 hockey...")
        return await self._fetch_sport_data('hockey')

    async def scrape_tennis(self) -> List[ScrapedEvent]:
        self.logger.info("Scraping Bet365 tennis...")
        return await self._fetch_sport_data('tennis')
