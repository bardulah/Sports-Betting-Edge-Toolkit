"""
Sharp vs Soft Comparator
========================

Compares odds between sharp (Pinnacle) and soft bookmakers
to identify market inefficiencies.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional
import logging
import pandas as pd

from ..scrapers.odds_aggregator import AggregatedEvent
from ..utils.odds_converter import OddsConverter


@dataclass
class OddsComparison:
    """Comparison between sharp and soft bookmaker odds."""
    event: AggregatedEvent
    selection: str
    sharp_odds: float
    soft_odds: Dict[str, float]  # {bookmaker: odds}
    best_soft_odds: float
    best_soft_book: str
    edge_percentage: float
    is_value: bool


class SharpSoftComparator:
    """
    Compares sharp and soft bookmaker odds to find value.

    Sharp books (like Pinnacle) have the most accurate odds.
    Soft books often have inefficiencies we can exploit.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("SharpSoftComparator")

        self.sharp_books = self.config.get('sharp_books', ['Pinnacle'])
        self.soft_books = self.config.get('soft_books', [
            'Tipsport', 'Fortuna', 'Niké', 'DOXXbet', 'Bet365'
        ])

        self.margin_method = 'power'

    def compare_event(self, event: AggregatedEvent) -> List[OddsComparison]:
        """
        Compare odds for a single event.

        Returns:
            List of comparisons for each selection
        """
        comparisons = []

        # Get sharp odds
        sharp_odds = None
        for sharp_book in self.sharp_books:
            if sharp_book in event.bookmaker_odds:
                sharp_odds = event.bookmaker_odds[sharp_book]
                break

        if not sharp_odds or 'moneyline' not in sharp_odds:
            return comparisons

        # Remove margin from sharp odds
        sharp_ml = sharp_odds['moneyline']
        fair_odds = OddsConverter.get_true_odds(
            list(sharp_ml.values()),
            self.margin_method
        )
        fair_odds_map = dict(zip(sharp_ml.keys(), fair_odds))

        # Compare each selection
        for selection, sharp_odd in sharp_ml.items():
            fair_odd = fair_odds_map.get(selection, sharp_odd)

            # Get soft book odds
            soft_odds = {}
            for book in self.soft_books:
                if book in event.bookmaker_odds:
                    book_ml = event.bookmaker_odds[book].get('moneyline', {})
                    if selection in book_ml:
                        soft_odds[book] = book_ml[selection]

            if not soft_odds:
                continue

            # Find best soft odds
            best_book = max(soft_odds, key=soft_odds.get)
            best_odds = soft_odds[best_book]

            # Calculate edge
            fair_prob = 1 / fair_odd
            offered_prob = 1 / best_odds
            edge = ((fair_prob - offered_prob) / offered_prob) * 100

            comparisons.append(OddsComparison(
                event=event,
                selection=selection,
                sharp_odds=sharp_odd,
                soft_odds=soft_odds,
                best_soft_odds=best_odds,
                best_soft_book=best_book,
                edge_percentage=round(edge, 2),
                is_value=edge > 0
            ))

        return comparisons

    def compare_all_events(
        self,
        events: List[AggregatedEvent],
        min_edge: float = 0
    ) -> List[OddsComparison]:
        """
        Compare all events and filter by minimum edge.
        """
        all_comparisons = []

        for event in events:
            comparisons = self.compare_event(event)
            for comp in comparisons:
                if comp.edge_percentage >= min_edge:
                    all_comparisons.append(comp)

        # Sort by edge
        all_comparisons.sort(key=lambda x: x.edge_percentage, reverse=True)

        return all_comparisons

    def get_market_efficiency_report(
        self,
        events: List[AggregatedEvent]
    ) -> pd.DataFrame:
        """
        Generate report on market efficiency by bookmaker.
        """
        data = {}

        for event in events:
            # Get sharp baseline
            sharp_odds = None
            for sharp_book in self.sharp_books:
                if sharp_book in event.bookmaker_odds:
                    sharp_odds = event.bookmaker_odds[sharp_book].get('moneyline', {})
                    break

            if not sharp_odds:
                continue

            # Calculate fair odds
            fair_odds = OddsConverter.get_true_odds(
                list(sharp_odds.values()),
                self.margin_method
            )
            fair_map = dict(zip(sharp_odds.keys(), fair_odds))

            # Compare each soft book
            for book in self.soft_books:
                if book not in event.bookmaker_odds:
                    continue

                if book not in data:
                    data[book] = {'edges': [], 'margins': []}

                book_ml = event.bookmaker_odds[book].get('moneyline', {})

                # Calculate edges for each selection
                for sel, soft_odd in book_ml.items():
                    if sel in fair_map:
                        fair_prob = 1 / fair_map[sel]
                        soft_prob = 1 / soft_odd
                        edge = (fair_prob - soft_prob) / soft_prob
                        data[book]['edges'].append(edge)

                # Calculate margin
                if book_ml:
                    margin = OddsConverter.calculate_margin(list(book_ml.values()))
                    data[book]['margins'].append(margin)

        # Build report
        rows = []
        for book, info in data.items():
            if info['edges']:
                avg_edge = sum(info['edges']) / len(info['edges']) * 100
                positive_edges = sum(1 for e in info['edges'] if e > 0)
                edge_rate = positive_edges / len(info['edges']) * 100
            else:
                avg_edge = 0
                edge_rate = 0

            avg_margin = sum(info['margins']) / len(info['margins']) * 100 if info['margins'] else 0

            rows.append({
                'bookmaker': book,
                'avg_margin': round(avg_margin, 2),
                'avg_edge_vs_sharp': round(avg_edge, 2),
                'value_frequency': round(edge_rate, 1),
                'samples': len(info['edges'])
            })

        return pd.DataFrame(rows).sort_values('avg_edge_vs_sharp', ascending=False)

    def find_steam_moves(
        self,
        events: List[AggregatedEvent],
        threshold: float = 5.0
    ) -> List[dict]:
        """
        Find significant odds movements (steam moves).

        Large differences between books can indicate sharp money.
        """
        steam_moves = []

        for event in events:
            all_odds = event.get_all_odds('moneyline')

            for selection, odds_list in all_odds.items():
                if len(odds_list) < 2:
                    continue

                # Sort by odds
                odds_list.sort(key=lambda x: x[0], reverse=True)

                highest = odds_list[0][0]
                lowest = odds_list[-1][0]

                # Calculate percentage difference
                diff_pct = ((highest - lowest) / lowest) * 100

                if diff_pct >= threshold:
                    steam_moves.append({
                        'event': event,
                        'selection': selection,
                        'highest_odds': highest,
                        'highest_book': odds_list[0][1],
                        'lowest_odds': lowest,
                        'lowest_book': odds_list[-1][1],
                        'difference_pct': round(diff_pct, 2),
                        'note': 'Significant odds discrepancy - possible value'
                    })

        return sorted(steam_moves, key=lambda x: x['difference_pct'], reverse=True)

    def get_best_value_by_selection(
        self,
        events: List[AggregatedEvent]
    ) -> Dict[str, List[dict]]:
        """
        Get best value bets organized by selection type.
        """
        value_by_sel = {'home': [], 'away': [], 'draw': []}

        for event in events:
            comparisons = self.compare_event(event)

            for comp in comparisons:
                if comp.is_value and comp.selection in value_by_sel:
                    value_by_sel[comp.selection].append({
                        'event': f"{event.home_team} vs {event.away_team}",
                        'odds': comp.best_soft_odds,
                        'book': comp.best_soft_book,
                        'edge': comp.edge_percentage
                    })

        # Sort each by edge
        for sel in value_by_sel:
            value_by_sel[sel].sort(key=lambda x: x['edge'], reverse=True)

        return value_by_sel
