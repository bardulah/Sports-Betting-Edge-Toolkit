"""
Niké Importer
=============

Import betting history from Niké export files.
"""

import pandas as pd
from datetime import datetime
from typing import Optional
import logging
import re

from .csv_importer import CSVImporter
from ..database.db_manager import DatabaseManager


class NikeImporter(CSVImporter):
    """
    Specialized importer for Niké betting history.
    """

    def __init__(self, db_manager: DatabaseManager = None):
        super().__init__(db_manager)
        self.logger = logging.getLogger("NikeImporter")
        self.bookmaker = 'nike'

    def import_nike_csv(self, filepath: str) -> int:
        """
        Import Niké betting history.

        Args:
            filepath: Path to Niké export CSV

        Returns:
            Number of bets imported
        """
        try:
            # Try different encodings common in Slovak exports
            for encoding in ['utf-8', 'cp1250', 'iso-8859-2']:
                try:
                    df = pd.read_csv(filepath, encoding=encoding, sep=';')
                    break
                except:
                    continue
            else:
                df = pd.read_csv(filepath)

        except Exception as e:
            self.logger.error(f"Failed to read Niké CSV: {e}")
            return 0

        self.logger.info(f"Read {len(df)} rows from Niké export")

        # Detect columns
        mapping = self._map_nike_columns(df)

        bets_data = []

        for _, row in df.iterrows():
            try:
                bet = self._parse_nike_row(row, mapping)
                if bet:
                    bets_data.append(bet)
            except Exception as e:
                self.logger.warning(f"Failed to parse row: {e}")
                continue

        if bets_data:
            count = self.db.import_bets(bets_data)
            self.logger.info(f"Imported {count} Niké bets")
            return count

        return 0

    def _map_nike_columns(self, df: pd.DataFrame) -> dict:
        """Map Niké columns to standard fields."""
        actual = {}
        columns = {c.lower(): c for c in df.columns}

        mappings = [
            ('event_name', ['udalosť', 'udalost', 'event', 'zápas', 'match']),
            ('selection', ['tip', 'stávka', 'bet', 'výběr']),
            ('odds', ['kurz', 'odd', 'odds']),
            ('stake', ['vklad', 'stake', 'suma', 'amount']),
            ('placed_at', ['dátum', 'datum', 'date']),
            ('status', ['stav', 'status', 'výsledok']),
            ('profit_loss', ['výhra', 'vyhra', 'win', 'zisk']),
            ('sport', ['šport', 'sport']),
            ('league', ['súťaž', 'liga', 'league'])
        ]

        for field, keywords in mappings:
            for kw in keywords:
                if kw in columns:
                    actual[field] = columns[kw]
                    break

        return actual

    def _parse_nike_row(self, row: pd.Series, mapping: dict) -> Optional[dict]:
        """Parse Niké row to bet data."""
        bet = {
            'source': 'nike_import',
            'imported': True
        }

        # Get bookmaker ID
        book = self.db.get_bookmaker(self.bookmaker)
        if book:
            bet['bookmaker_id'] = book.id

        # Selection
        if 'selection' in mapping:
            bet['selection'] = str(row[mapping['selection']])
        else:
            return None

        # Odds
        if 'odds' in mapping:
            odds = row[mapping['odds']]
            if isinstance(odds, str):
                odds = odds.replace(',', '.').strip()
            bet['odds'] = float(odds)
        else:
            return None

        # Stake
        if 'stake' in mapping:
            stake = row[mapping['stake']]
            if isinstance(stake, str):
                stake = re.sub(r'[€\s]', '', stake).replace(',', '.')
            bet['stake'] = float(stake)
        else:
            return None

        # Event
        if 'event_name' in mapping:
            bet['event_name'] = str(row[mapping['event_name']])

        # Date
        if 'placed_at' in mapping:
            try:
                date_str = str(row[mapping['placed_at']])
                for fmt in ['%d.%m.%Y %H:%M', '%d.%m.%Y', '%Y-%m-%d %H:%M:%S']:
                    try:
                        bet['placed_at'] = datetime.strptime(date_str, fmt)
                        break
                    except:
                        continue
                else:
                    bet['placed_at'] = datetime.now()
            except:
                bet['placed_at'] = datetime.now()

        # Status
        if 'status' in mapping:
            status = str(row[mapping['status']]).lower()
            if any(w in status for w in ['výhra', 'vyhra', 'won', 'win']):
                bet['status'] = 'won'
            elif any(w in status for w in ['prehra', 'lost', 'loss']):
                bet['status'] = 'lost'
            elif any(w in status for w in ['zrušen', 'void', 'storno']):
                bet['status'] = 'void'
            else:
                bet['status'] = 'pending'

        # Profit/Loss
        if 'profit_loss' in mapping:
            pl = row[mapping['profit_loss']]
            if pd.notna(pl):
                if isinstance(pl, str):
                    pl = re.sub(r'[€\s]', '', pl).replace(',', '.')
                bet['profit_loss'] = float(pl)
                if bet['status'] == 'won':
                    bet['actual_return'] = bet['stake'] + float(pl)
                else:
                    bet['actual_return'] = 0
        else:
            if bet.get('status') == 'won':
                bet['profit_loss'] = bet['stake'] * (bet['odds'] - 1)
                bet['actual_return'] = bet['stake'] * bet['odds']
            elif bet.get('status') == 'lost':
                bet['profit_loss'] = -bet['stake']
                bet['actual_return'] = 0

        # Sport
        if 'sport' in mapping:
            sport = str(row[mapping['sport']]).lower()
            if 'futbal' in sport:
                sport = 'football'
            elif 'hokej' in sport:
                sport = 'hockey'
            elif 'tenis' in sport:
                sport = 'tennis'
            bet['sport'] = sport

        # League
        if 'league' in mapping:
            bet['league'] = str(row[mapping['league']])

        bet['potential_return'] = bet['stake'] * bet['odds']

        return bet

    def import_nike_excel(self, filepath: str) -> int:
        """
        Import from Niké Excel export.

        Args:
            filepath: Path to Excel file

        Returns:
            Number of bets imported
        """
        try:
            df = pd.read_excel(filepath)
        except Exception as e:
            self.logger.error(f"Failed to read Excel: {e}")
            return 0

        # Same parsing logic
        mapping = self._map_nike_columns(df)
        bets_data = []

        for _, row in df.iterrows():
            try:
                bet = self._parse_nike_row(row, mapping)
                if bet:
                    bets_data.append(bet)
            except:
                continue

        if bets_data:
            return self.db.import_bets(bets_data)

        return 0
