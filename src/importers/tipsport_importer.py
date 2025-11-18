"""
Tipsport Importer
=================

Import betting history from Tipsport export files.
"""

import pandas as pd
from datetime import datetime
from typing import Optional
import logging
import re

from .csv_importer import CSVImporter
from ..database.db_manager import DatabaseManager


class TipsportImporter(CSVImporter):
    """
    Specialized importer for Tipsport betting history.

    Tipsport exports history in a specific format that this class handles.
    """

    def __init__(self, db_manager: DatabaseManager = None):
        super().__init__(db_manager)
        self.logger = logging.getLogger("TipsportImporter")
        self.bookmaker = 'tipsport'

        # Tipsport-specific column mappings
        # These may need adjustment based on actual export format
        self.column_mapping = {
            'event_name': 'Udalosť',
            'selection': 'Tip',
            'odds': 'Kurz',
            'stake': 'Vklad',
            'placed_at': 'Dátum',
            'status': 'Stav',
            'profit_loss': 'Výhra',
            'sport': 'Šport',
            'league': 'Súťaž'
        }

    def import_tipsport_csv(self, filepath: str) -> int:
        """
        Import Tipsport betting history.

        Args:
            filepath: Path to Tipsport export CSV

        Returns:
            Number of bets imported
        """
        try:
            # Try different encodings
            for encoding in ['utf-8', 'cp1250', 'iso-8859-2']:
                try:
                    df = pd.read_csv(filepath, encoding=encoding, sep=';')
                    break
                except:
                    continue
            else:
                df = pd.read_csv(filepath)

        except Exception as e:
            self.logger.error(f"Failed to read Tipsport CSV: {e}")
            return 0

        self.logger.info(f"Read {len(df)} rows from Tipsport export")

        # Detect actual columns
        actual_mapping = self._map_tipsport_columns(df)

        bets_data = []

        for _, row in df.iterrows():
            try:
                bet = self._parse_tipsport_row(row, actual_mapping)
                if bet:
                    bets_data.append(bet)
            except Exception as e:
                self.logger.warning(f"Failed to parse row: {e}")
                continue

        if bets_data:
            count = self.db.import_bets(bets_data)
            self.logger.info(f"Imported {count} Tipsport bets")
            return count

        return 0

    def _map_tipsport_columns(self, df: pd.DataFrame) -> dict:
        """Map Tipsport columns to standard fields."""
        actual = {}
        columns = {c.lower(): c for c in df.columns}

        mappings = [
            ('event_name', ['udalosť', 'udalost', 'event', 'zápas', 'zapas']),
            ('selection', ['tip', 'stávka', 'stavka', 'výběr']),
            ('odds', ['kurz', 'odd', 'rate']),
            ('stake', ['vklad', 'stake', 'čiastka', 'suma']),
            ('placed_at', ['dátum', 'datum', 'date', 'čas']),
            ('status', ['stav', 'status', 'výsledok', 'vysledok']),
            ('profit_loss', ['výhra', 'vyhra', 'win', 'zisk', 'profit']),
            ('sport', ['šport', 'sport']),
            ('league', ['súťaž', 'sutaz', 'liga', 'competition'])
        ]

        for field, keywords in mappings:
            for kw in keywords:
                if kw in columns:
                    actual[field] = columns[kw]
                    break

        return actual

    def _parse_tipsport_row(self, row: pd.Series, mapping: dict) -> Optional[dict]:
        """Parse Tipsport row to bet data."""
        bet = {
            'source': 'tipsport_import',
            'imported': True
        }

        # Get bookmaker ID
        book = self.db.get_bookmaker(self.bookmaker)
        if book:
            bet['bookmaker_id'] = book.id

        # Parse selection
        if 'selection' in mapping:
            bet['selection'] = str(row[mapping['selection']])
        else:
            return None

        # Parse odds
        if 'odds' in mapping:
            odds = row[mapping['odds']]
            if isinstance(odds, str):
                odds = odds.replace(',', '.').strip()
            bet['odds'] = float(odds)
        else:
            return None

        # Parse stake
        if 'stake' in mapping:
            stake = row[mapping['stake']]
            if isinstance(stake, str):
                # Remove currency symbols and spaces
                stake = re.sub(r'[€\s]', '', stake).replace(',', '.')
            bet['stake'] = float(stake)
        else:
            return None

        # Parse event name
        if 'event_name' in mapping:
            bet['event_name'] = str(row[mapping['event_name']])

        # Parse date
        if 'placed_at' in mapping:
            try:
                date_str = str(row[mapping['placed_at']])
                # Try common Tipsport date formats
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

        # Parse status
        if 'status' in mapping:
            status = str(row[mapping['status']]).lower()
            if any(w in status for w in ['výhra', 'vyhra', 'won', 'win', 'vyhral']):
                bet['status'] = 'won'
            elif any(w in status for w in ['prehra', 'lost', 'loss', 'prehral']):
                bet['status'] = 'lost'
            elif any(w in status for w in ['zrušen', 'void', 'cancel', 'storno']):
                bet['status'] = 'void'
            else:
                bet['status'] = 'pending'

        # Parse profit/loss
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

        # Sport and league
        if 'sport' in mapping:
            sport = str(row[mapping['sport']]).lower()
            if 'futbal' in sport or 'fotbal' in sport:
                sport = 'football'
            elif 'hokej' in sport:
                sport = 'hockey'
            elif 'tenis' in sport:
                sport = 'tennis'
            bet['sport'] = sport

        if 'league' in mapping:
            bet['league'] = str(row[mapping['league']])

        # Calculate potential return
        bet['potential_return'] = bet['stake'] * bet['odds']

        return bet

    def parse_tipsport_ticket(self, ticket_text: str) -> list:
        """
        Parse a Tipsport ticket from text (e.g., screenshot OCR).

        Args:
            ticket_text: Text of the ticket

        Returns:
            List of bet dictionaries
        """
        bets = []
        lines = ticket_text.split('\n')

        # Basic parsing - would need adjustment for actual format
        for line in lines:
            # Look for odds pattern
            odds_match = re.search(r'(\d+[,\.]\d{2})', line)
            if odds_match:
                # This is a simplified parser
                pass

        return bets
