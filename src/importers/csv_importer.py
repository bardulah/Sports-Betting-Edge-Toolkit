"""
CSV Importer
============

Import betting history from CSV files.
"""

import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
import logging
import re

from ..database.db_manager import DatabaseManager


class CSVImporter:
    """
    Generic CSV importer for betting history.
    """

    def __init__(self, db_manager: DatabaseManager = None):
        self.db = db_manager or DatabaseManager()
        self.logger = logging.getLogger("CSVImporter")

    def import_csv(
        self,
        filepath: str,
        column_mapping: Dict[str, str] = None,
        bookmaker: str = 'Unknown',
        date_format: str = '%Y-%m-%d %H:%M:%S'
    ) -> int:
        """
        Import bets from CSV file.

        Args:
            filepath: Path to CSV file
            column_mapping: Map CSV columns to bet fields
            bookmaker: Default bookmaker name
            date_format: Date format in CSV

        Returns:
            Number of bets imported
        """
        try:
            df = pd.read_csv(filepath)
        except Exception as e:
            self.logger.error(f"Failed to read CSV: {e}")
            return 0

        self.logger.info(f"Read {len(df)} rows from {filepath}")

        # Default column mapping
        if column_mapping is None:
            column_mapping = self._detect_columns(df)

        bets_data = []

        for _, row in df.iterrows():
            try:
                bet = self._parse_row(row, column_mapping, bookmaker, date_format)
                if bet:
                    bets_data.append(bet)
            except Exception as e:
                self.logger.warning(f"Failed to parse row: {e}")
                continue

        if bets_data:
            count = self.db.import_bets(bets_data)
            self.logger.info(f"Imported {count} bets")
            return count

        return 0

    def _detect_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """Attempt to auto-detect column mapping."""
        columns = df.columns.str.lower()
        mapping = {}

        # Common column patterns
        patterns = {
            'event_name': ['event', 'match', 'zápas', 'udalost'],
            'selection': ['selection', 'tip', 'výběr', 'stávka', 'bet'],
            'odds': ['odds', 'kurz', 'odd', 'rate'],
            'stake': ['stake', 'vklad', 'amount', 'čiastka', 'suma'],
            'placed_at': ['date', 'time', 'dátum', 'čas', 'placed'],
            'status': ['status', 'result', 'výsledok', 'stav'],
            'profit_loss': ['profit', 'pl', 'zisk', 'win', 'výhra'],
            'sport': ['sport', 'šport'],
            'league': ['league', 'competition', 'liga', 'súťaž']
        }

        for field, keywords in patterns.items():
            for col in df.columns:
                col_lower = col.lower()
                if any(kw in col_lower for kw in keywords):
                    mapping[field] = col
                    break

        return mapping

    def _parse_row(
        self,
        row: pd.Series,
        mapping: Dict[str, str],
        bookmaker: str,
        date_format: str
    ) -> Optional[dict]:
        """Parse a single row to bet data."""
        bet = {
            'source': 'csv_import',
            'imported': True
        }

        # Get bookmaker ID
        book = self.db.get_bookmaker(bookmaker.lower())
        if book:
            bet['bookmaker_id'] = book.id

        # Required fields
        if 'selection' in mapping:
            bet['selection'] = str(row[mapping['selection']])
        else:
            return None

        if 'odds' in mapping:
            odds = row[mapping['odds']]
            if isinstance(odds, str):
                odds = float(odds.replace(',', '.'))
            bet['odds'] = float(odds)
        else:
            return None

        if 'stake' in mapping:
            stake = row[mapping['stake']]
            if isinstance(stake, str):
                stake = float(stake.replace(',', '.').replace('€', '').strip())
            bet['stake'] = float(stake)
        else:
            return None

        # Optional fields
        if 'event_name' in mapping:
            bet['event_name'] = str(row[mapping['event_name']])

        if 'placed_at' in mapping:
            try:
                date_val = row[mapping['placed_at']]
                if isinstance(date_val, str):
                    bet['placed_at'] = datetime.strptime(date_val, date_format)
                else:
                    bet['placed_at'] = pd.to_datetime(date_val)
            except:
                bet['placed_at'] = datetime.now()

        if 'status' in mapping:
            status = str(row[mapping['status']]).lower()
            if any(w in status for w in ['won', 'win', 'výhra', 'vyhral']):
                bet['status'] = 'won'
            elif any(w in status for w in ['lost', 'loss', 'prehra', 'prehral']):
                bet['status'] = 'lost'
            elif any(w in status for w in ['void', 'cancel', 'zrušen']):
                bet['status'] = 'void'
            else:
                bet['status'] = 'pending'

        if 'profit_loss' in mapping:
            pl = row[mapping['profit_loss']]
            if isinstance(pl, str):
                pl = float(pl.replace(',', '.').replace('€', '').strip())
            bet['profit_loss'] = float(pl)
        elif bet.get('status') == 'won':
            bet['profit_loss'] = bet['stake'] * (bet['odds'] - 1)
            bet['actual_return'] = bet['stake'] * bet['odds']
        elif bet.get('status') == 'lost':
            bet['profit_loss'] = -bet['stake']
            bet['actual_return'] = 0

        if 'sport' in mapping:
            bet['sport'] = str(row[mapping['sport']]).lower()

        if 'league' in mapping:
            bet['league'] = str(row[mapping['league']])

        # Calculate potential return
        bet['potential_return'] = bet['stake'] * bet['odds']

        return bet

    def preview_import(self, filepath: str, rows: int = 5) -> pd.DataFrame:
        """Preview CSV file before importing."""
        try:
            df = pd.read_csv(filepath, nrows=rows)
            return df
        except Exception as e:
            self.logger.error(f"Failed to preview CSV: {e}")
            return pd.DataFrame()

    def get_import_stats(self, filepath: str) -> dict:
        """Get statistics about a CSV file before importing."""
        try:
            df = pd.read_csv(filepath)
            mapping = self._detect_columns(df)

            stats = {
                'total_rows': len(df),
                'columns': list(df.columns),
                'detected_mapping': mapping
            }

            if 'stake' in mapping:
                stakes = df[mapping['stake']].apply(
                    lambda x: float(str(x).replace(',', '.').replace('€', ''))
                    if pd.notna(x) else 0
                )
                stats['total_staked'] = round(stakes.sum(), 2)
                stats['avg_stake'] = round(stakes.mean(), 2)

            if 'odds' in mapping:
                odds = df[mapping['odds']].apply(
                    lambda x: float(str(x).replace(',', '.'))
                    if pd.notna(x) else 0
                )
                stats['avg_odds'] = round(odds.mean(), 3)

            return stats

        except Exception as e:
            return {'error': str(e)}
