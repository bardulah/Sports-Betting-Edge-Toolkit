"""
Slovak Bookmaker Scraper Adapter
================================

Adapter interface for Slovak bookmaker scrapers.

IMPORTANT: This is an ADAPTER - you need to provide a working scraper implementation.

Options:
1. Use a community scraper (check GitHub for current working solutions)
2. Build your own with Playwright + stealth plugins
3. Use a scraping service/proxy

The adapter expects scrapers to return data in a standard format.
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Optional, Protocol
from dataclasses import dataclass, field
import importlib
import subprocess
import sys

logger = logging.getLogger(__name__)


@dataclass
class SlovakScrapedEvent:
    """Standardized event from Slovak bookmaker."""
    bookmaker: str  # tipsport, fortuna, nike, doxxbet
    external_id: str
    sport: str
    league: str
    home_team: str
    away_team: str
    start_time: datetime
    odds: Dict[str, Dict[str, float]]  # {market: {selection: odds}}
    url: Optional[str] = None


class SlovakScraperProtocol(Protocol):
    """Protocol that Slovak scrapers must implement."""

    async def scrape_football(self) -> List[SlovakScrapedEvent]: ...
    async def scrape_hockey(self) -> List[SlovakScrapedEvent]: ...
    async def scrape_tennis(self) -> List[SlovakScrapedEvent]: ...
    async def close(self) -> None: ...


class SlovakScraperAdapter:
    """
    Adapter for Slovak bookmaker scrapers.

    This adapter can work with:
    1. External scraper packages (pip install)
    2. Local scraper modules
    3. Subprocess calls to standalone scrapers
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.scrapers: Dict[str, SlovakScraperProtocol] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize scrapers based on configuration."""
        if self._initialized:
            return

        scraper_config = self.config.get('slovak_scrapers', {})

        # Try to load configured scrapers
        for bookmaker in ['tipsport', 'fortuna', 'nike', 'doxxbet']:
            book_config = scraper_config.get(bookmaker, {})

            if not book_config.get('enabled', True):
                logger.info(f"Scraper for {bookmaker} disabled")
                continue

            scraper = await self._load_scraper(bookmaker, book_config)
            if scraper:
                self.scrapers[bookmaker] = scraper
                logger.info(f"Loaded scraper for {bookmaker}")
            else:
                logger.warning(f"No scraper available for {bookmaker}")

        self._initialized = True

    async def _load_scraper(
        self,
        bookmaker: str,
        config: dict
    ) -> Optional[SlovakScraperProtocol]:
        """Load a scraper based on configuration."""

        # Option 1: External package
        package = config.get('package')
        if package:
            try:
                module = importlib.import_module(package)
                scraper_class = getattr(module, config.get('class', 'Scraper'))
                return scraper_class(config)
            except ImportError as e:
                logger.error(f"Failed to import {package}: {e}")
                logger.info(f"Try: pip install {package}")

        # Option 2: Local module path
        module_path = config.get('module')
        if module_path:
            try:
                spec = importlib.util.spec_from_file_location("scraper", module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                scraper_class = getattr(module, config.get('class', 'Scraper'))
                return scraper_class(config)
            except Exception as e:
                logger.error(f"Failed to load module {module_path}: {e}")

        # Option 3: Use stub scraper (returns empty - for manual entry fallback)
        return StubScraper(bookmaker)

    async def scrape_all(self, sport: str = None) -> Dict[str, List[SlovakScrapedEvent]]:
        """
        Scrape all Slovak bookmakers.

        Args:
            sport: Optional filter ('football', 'hockey', 'tennis')

        Returns:
            Dict of {bookmaker: [events]}
        """
        await self.initialize()

        results = {}

        for bookmaker, scraper in self.scrapers.items():
            try:
                events = []

                if sport is None or sport == 'football':
                    events.extend(await scraper.scrape_football())

                if sport is None or sport == 'hockey':
                    events.extend(await scraper.scrape_hockey())

                if sport is None or sport == 'tennis':
                    events.extend(await scraper.scrape_tennis())

                results[bookmaker] = events
                logger.info(f"Scraped {len(events)} events from {bookmaker}")

            except Exception as e:
                logger.error(f"Error scraping {bookmaker}: {e}")
                results[bookmaker] = []

        return results

    async def scrape_bookmaker(
        self,
        bookmaker: str,
        sport: str = None
    ) -> List[SlovakScrapedEvent]:
        """Scrape a specific bookmaker."""
        await self.initialize()

        if bookmaker not in self.scrapers:
            logger.warning(f"No scraper for {bookmaker}")
            return []

        scraper = self.scrapers[bookmaker]
        events = []

        try:
            if sport is None or sport == 'football':
                events.extend(await scraper.scrape_football())
            if sport is None or sport == 'hockey':
                events.extend(await scraper.scrape_hockey())
            if sport is None or sport == 'tennis':
                events.extend(await scraper.scrape_tennis())
        except Exception as e:
            logger.error(f"Error scraping {bookmaker}: {e}")

        return events

    async def close(self):
        """Close all scrapers."""
        for scraper in self.scrapers.values():
            try:
                await scraper.close()
            except:
                pass


class StubScraper:
    """
    Stub scraper that returns empty results.
    Used when no real scraper is configured.
    """

    def __init__(self, bookmaker: str):
        self.bookmaker = bookmaker

    async def scrape_football(self) -> List[SlovakScrapedEvent]:
        logger.debug(f"Stub scraper for {self.bookmaker} - no data")
        return []

    async def scrape_hockey(self) -> List[SlovakScrapedEvent]:
        return []

    async def scrape_tennis(self) -> List[SlovakScrapedEvent]:
        return []

    async def close(self):
        pass


class PlaywrightSlovakScraper:
    """
    Base Playwright scraper for Slovak bookmakers.

    This is a TEMPLATE - you'll need to fill in the actual selectors
    and parsing logic for each bookmaker by inspecting their sites.

    Uses:
    - Playwright with stealth plugin
    - Rotating user agents
    - Optional proxy support
    """

    def __init__(self, bookmaker: str, config: dict = None):
        self.bookmaker = bookmaker
        self.config = config or {}
        self.browser = None
        self.context = None

        # URLs - FILL THESE IN
        self.urls = {
            'tipsport': {
                'football': 'https://www.tipsport.sk/kurzy/futbal',
                'hockey': 'https://www.tipsport.sk/kurzy/hokej',
                'tennis': 'https://www.tipsport.sk/kurzy/tenis',
            },
            'fortuna': {
                'football': 'https://www.ifortuna.sk/tipovanie/futbal',
                'hockey': 'https://www.ifortuna.sk/tipovanie/hokej',
                'tennis': 'https://www.ifortuna.sk/tipovanie/tenis',
            },
            'nike': {
                'football': 'https://www.nike.sk/tipovanie/futbal',
                'hockey': 'https://www.nike.sk/tipovanie/hokej',
                'tennis': 'https://www.nike.sk/tipovanie/tenis',
            },
            'doxxbet': {
                'football': 'https://www.doxxbet.sk/tipovanie/futbal',
                'hockey': 'https://www.doxxbet.sk/tipovanie/hokej',
                'tennis': 'https://www.doxxbet.sk/tipovanie/tenis',
            },
        }

    async def _init_browser(self):
        """Initialize Playwright browser with stealth."""
        if self.browser:
            return

        from playwright.async_api import async_playwright

        # Try to use stealth plugin
        try:
            from playwright_stealth import stealth_async
            self._use_stealth = True
        except ImportError:
            logger.warning("playwright-stealth not installed. Install for better results.")
            self._use_stealth = False

        playwright = await async_playwright().start()

        # Browser args for stealth
        args = [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
        ]

        # Proxy if configured
        proxy = None
        if self.config.get('proxy'):
            proxy = {'server': self.config['proxy']}

        self.browser = await playwright.chromium.launch(
            headless=self.config.get('headless', True),
            args=args
        )

        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            proxy=proxy
        )

    async def _get_page_content(self, url: str) -> str:
        """Get page content with stealth."""
        await self._init_browser()

        page = await self.context.new_page()

        try:
            # Apply stealth if available
            if hasattr(self, '_use_stealth') and self._use_stealth:
                from playwright_stealth import stealth_async
                await stealth_async(page)

            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)  # Wait for dynamic content

            return await page.content()

        finally:
            await page.close()

    async def scrape_football(self) -> List[SlovakScrapedEvent]:
        """Override this with actual parsing logic."""
        raise NotImplementedError("Implement parsing for your target site")

    async def scrape_hockey(self) -> List[SlovakScrapedEvent]:
        raise NotImplementedError()

    async def scrape_tennis(self) -> List[SlovakScrapedEvent]:
        raise NotImplementedError()

    async def close(self):
        if self.browser:
            await self.browser.close()


# Example config for config.yaml:
"""
slovak_scrapers:
  tipsport:
    enabled: true
    # Option 1: External package
    package: "slovak_odds_scraper"
    class: "TipsportScraper"

    # Option 2: Local module
    # module: "/path/to/scraper.py"
    # class: "TipsportScraper"

    # Optional proxy
    proxy: "http://user:pass@proxy:port"
    headless: true

  fortuna:
    enabled: true
    package: "slovak_odds_scraper"
    class: "FortunaScraper"

  nike:
    enabled: true
    package: "slovak_odds_scraper"
    class: "NikeScraper"

  doxxbet:
    enabled: true
    package: "slovak_odds_scraper"
    class: "DoxxbetScraper"
"""
