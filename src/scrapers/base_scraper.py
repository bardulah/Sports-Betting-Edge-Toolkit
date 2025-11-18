"""
Base Scraper Module
===================

Abstract base class for all bookmaker scrapers.
"""

import asyncio
import aiohttp
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from fake_useragent import UserAgent

import cloudscraper
from bs4 import BeautifulSoup


@dataclass
class ScrapedOdds:
    """Data class for scraped odds."""
    bookmaker: str
    sport: str
    league: str
    home_team: str
    away_team: str
    start_time: datetime
    market_type: str
    selection: str
    odds: float
    line: Optional[float] = None
    is_live: bool = False
    external_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ScrapedEvent:
    """Data class for scraped event."""
    bookmaker: str
    external_id: str
    sport: str
    league: str
    home_team: str
    away_team: str
    start_time: datetime
    is_live: bool = False
    odds: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # odds format: {market_type: {selection: odds_value}}


class BaseScraper(ABC):
    """
    Abstract base class for bookmaker scrapers.

    All bookmaker-specific scrapers should inherit from this class.
    """

    def __init__(self, config: dict = None):
        """Initialize scraper."""
        self.config = config or {}
        self.name = self.__class__.__name__.replace('Scraper', '')
        self.logger = logging.getLogger(f"scraper.{self.name}")

        self.ua = UserAgent()
        self.session = None
        self.cloudscraper = cloudscraper.create_scraper()

        # Rate limiting
        self.rate_limit = self.config.get('rate_limit_per_second', 2)
        self.last_request_time = 0

        # Headers
        self.headers = {
            'User-Agent': self.ua.random,
            'Accept': 'application/json, text/html, */*',
            'Accept-Language': 'sk-SK,sk;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout
            )
        return self.session

    async def close(self):
        """Close session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def _rate_limit_wait(self):
        """Wait for rate limiting."""
        import time
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        wait_time = (1 / self.rate_limit) - elapsed

        if wait_time > 0:
            await asyncio.sleep(wait_time)

        self.last_request_time = time.time()

    async def fetch(self, url: str, method: str = 'GET', **kwargs) -> Optional[str]:
        """Fetch URL with rate limiting and error handling."""
        await self._rate_limit_wait()

        try:
            session = await self._get_session()

            async with session.request(method, url, **kwargs) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    self.logger.warning(f"HTTP {response.status} for {url}")
                    return None

        except asyncio.TimeoutError:
            self.logger.error(f"Timeout fetching {url}")
            return None
        except Exception as e:
            self.logger.error(f"Error fetching {url}: {e}")
            return None

    async def fetch_json(self, url: str, method: str = 'GET', **kwargs) -> Optional[dict]:
        """Fetch URL and parse as JSON."""
        await self._rate_limit_wait()

        try:
            session = await self._get_session()

            async with session.request(method, url, **kwargs) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    self.logger.warning(f"HTTP {response.status} for {url}")
                    return None

        except asyncio.TimeoutError:
            self.logger.error(f"Timeout fetching {url}")
            return None
        except Exception as e:
            self.logger.error(f"Error fetching {url}: {e}")
            return None

    def fetch_with_cloudscraper(self, url: str) -> Optional[str]:
        """Fetch URL using cloudscraper (bypasses some anti-bot measures)."""
        try:
            response = self.cloudscraper.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.text
            else:
                self.logger.warning(f"HTTP {response.status_code} for {url}")
                return None
        except Exception as e:
            self.logger.error(f"Cloudscraper error for {url}: {e}")
            return None

    @abstractmethod
    async def scrape_football(self) -> List[ScrapedEvent]:
        """Scrape football/soccer odds."""
        pass

    @abstractmethod
    async def scrape_hockey(self) -> List[ScrapedEvent]:
        """Scrape hockey odds."""
        pass

    @abstractmethod
    async def scrape_tennis(self) -> List[ScrapedEvent]:
        """Scrape tennis odds."""
        pass

    async def scrape_all(self) -> Dict[str, List[ScrapedEvent]]:
        """Scrape all sports."""
        results = {}

        try:
            results['football'] = await self.scrape_football()
        except Exception as e:
            self.logger.error(f"Error scraping football: {e}")
            results['football'] = []

        try:
            results['hockey'] = await self.scrape_hockey()
        except Exception as e:
            self.logger.error(f"Error scraping hockey: {e}")
            results['hockey'] = []

        try:
            results['tennis'] = await self.scrape_tennis()
        except Exception as e:
            self.logger.error(f"Error scraping tennis: {e}")
            results['tennis'] = []

        await self.close()
        return results

    def parse_odds(self, odds_str: str) -> Optional[float]:
        """Parse odds string to float."""
        try:
            # Remove whitespace and common characters
            cleaned = odds_str.strip().replace(',', '.').replace(' ', '')
            return float(cleaned)
        except (ValueError, AttributeError):
            return None

    def normalize_team_name(self, name: str) -> str:
        """Normalize team name for matching."""
        # Remove common suffixes
        suffixes = ['FC', 'FK', 'SK', 'HC', 'AC', 'AS', 'SC', 'CF', 'CD', 'Real', 'Dynamo']

        normalized = name.strip()
        for suffix in suffixes:
            normalized = normalized.replace(f' {suffix}', '').replace(f'{suffix} ', '')

        return normalized.strip().lower()

    def parse_datetime(self, date_str: str, time_str: str = None) -> Optional[datetime]:
        """Parse date/time strings to datetime."""
        formats = [
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d %H:%M:%S',
            '%d.%m.%Y %H:%M',
            '%d.%m.%Y %H:%M:%S',
            '%d/%m/%Y %H:%M',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%SZ',
        ]

        if time_str:
            date_str = f"{date_str} {time_str}"

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        return None

    def extract_markets(self, event_data: dict) -> Dict[str, Dict[str, float]]:
        """
        Extract all markets from event data.
        Override in subclass for specific bookmaker format.

        Returns: {market_type: {selection: odds_value}}
        """
        return {}

    @staticmethod
    def calculate_margin(odds_list: List[float]) -> float:
        """Calculate bookmaker margin from odds."""
        if not odds_list or any(o <= 0 for o in odds_list):
            return 0.0
        return sum(1/o for o in odds_list) - 1


class SeleniumScraperMixin:
    """
    Mixin for scrapers that need Selenium/Playwright for JavaScript rendering.
    """

    def __init__(self):
        self.driver = None
        self.playwright = None
        self.browser = None

    async def init_playwright(self):
        """Initialize Playwright browser."""
        from playwright.async_api import async_playwright

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )

    async def get_page_content(self, url: str, wait_selector: str = None) -> str:
        """Get page content using Playwright."""
        if not self.browser:
            await self.init_playwright()

        page = await self.browser.new_page()

        try:
            await page.goto(url, wait_until='networkidle')

            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout=10000)

            content = await page.content()
            return content

        finally:
            await page.close()

    async def close_browser(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    def init_selenium(self, headless: bool = True):
        """Initialize Selenium WebDriver."""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        options = Options()
        if headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument(f'user-agent={self.ua.random}')

        self.driver = webdriver.Chrome(options=options)

    def selenium_get(self, url: str) -> str:
        """Get page content using Selenium."""
        if not self.driver:
            self.init_selenium()

        self.driver.get(url)
        return self.driver.page_source

    def close_selenium(self):
        """Close Selenium driver."""
        if self.driver:
            self.driver.quit()
