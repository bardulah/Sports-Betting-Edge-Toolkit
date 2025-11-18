"""
EV Calculator
=============

Calculates Expected Value for betting opportunities by comparing
soft bookmaker odds against sharp bookmaker (Pinnacle) true odds.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

from ..utils.odds_converter import OddsConverter
from ..utils.probability_utils import ProbabilityUtils
from ..scrapers.odds_aggregator import AggregatedEvent


@dataclass
class EVOpportunity:
    """Represents a positive EV betting opportunity."""
    event: AggregatedEvent
    bookmaker: str
    market_type: str
    selection: str
    offered_odds: float
    true_probability: float
    sharp_odds: float
    ev_percentage: float
    edge: float
    kelly_stake: float
    recommended_stake: float
    confidence: str  # 'high', 'medium', 'low'
    detected_at: datetime = field(default_factory=datetime.now)

    def __str__(self):
        return (
            f"+{self.ev_percentage:.1f}% EV | {self.event.home_team} vs {self.event.away_team} | "
            f"{self.selection} @ {self.offered_odds} ({self.bookmaker}) | "
            f"Sharp: {self.sharp_odds}"
        )


class EVCalculator:
    """
    Calculates Expected Value for betting opportunities.

    Uses Pinnacle odds as the sharp baseline to determine true probabilities,
    then compares against soft bookmaker odds to find +EV opportunities.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("EVCalculator")

        # Configuration
        self.min_ev = self.config.get('min_ev_percentage', 2.0)
        self.sharp_books = self.config.get('sharp_books', ['Pinnacle'])
        self.soft_books = self.config.get('soft_books', [
            'Tipsport', 'Fortuna', 'Niké', 'DOXXbet', 'Bet365'
        ])

        # Margin removal method
        self.margin_method = self.config.get('margin_removal_method', 'power')

        # Kelly settings
        self.kelly_fraction = self.config.get('kelly_fraction', 0.25)
        self.max_bet_pct = self.config.get('max_bet_percentage', 0.05)
        self.bankroll = self.config.get('current_bankroll', 1000)

    def find_ev_opportunities(
        self,
        events: List[AggregatedEvent],
        min_ev: float = None
    ) -> List[EVOpportunity]:
        """
        Find all +EV opportunities across events.

        Args:
            events: List of aggregated events with odds from multiple books
            min_ev: Minimum EV percentage to report

        Returns:
            List of EVOpportunity sorted by EV descending
        """
        min_ev = min_ev if min_ev is not None else self.min_ev
        opportunities = []

        for event in events:
            event_opps = self._analyze_event(event, min_ev)
            opportunities.extend(event_opps)

        # Sort by EV percentage
        opportunities.sort(key=lambda x: x.ev_percentage, reverse=True)

        return opportunities

    def _analyze_event(self, event: AggregatedEvent, min_ev: float) -> List[EVOpportunity]:
        """Analyze a single event for +EV opportunities."""
        opportunities = []

        # Get sharp odds (Pinnacle)
        sharp_odds = self._get_sharp_odds(event)
        if not sharp_odds:
            return opportunities

        # Calculate true probabilities
        true_probs = self._calculate_true_probabilities(sharp_odds)
        if not true_probs:
            return opportunities

        # Check each soft bookmaker
        for bookmaker in self.soft_books:
            if bookmaker not in event.bookmaker_odds:
                continue

            book_odds = event.bookmaker_odds[bookmaker]

            # Check moneyline market
            if 'moneyline' in book_odds and 'moneyline' in sharp_odds:
                for selection, offered_odds in book_odds['moneyline'].items():
                    if selection not in true_probs['moneyline']:
                        continue

                    true_prob = true_probs['moneyline'][selection]
                    sharp_odd = sharp_odds['moneyline'].get(selection, 0)

                    # Calculate EV
                    ev_pct = self._calculate_ev_percentage(true_prob, offered_odds)
                    edge = self._calculate_edge(true_prob, offered_odds)

                    if ev_pct >= min_ev:
                        # Calculate Kelly stake
                        kelly = ProbabilityUtils.fractional_kelly(
                            true_prob, offered_odds, self.kelly_fraction
                        )
                        recommended = min(kelly, self.max_bet_pct) * self.bankroll

                        # Determine confidence
                        confidence = self._determine_confidence(ev_pct, edge, len(event.bookmaker_odds))

                        opportunity = EVOpportunity(
                            event=event,
                            bookmaker=bookmaker,
                            market_type='moneyline',
                            selection=selection,
                            offered_odds=offered_odds,
                            true_probability=true_prob,
                            sharp_odds=sharp_odd,
                            ev_percentage=ev_pct,
                            edge=edge,
                            kelly_stake=kelly,
                            recommended_stake=round(recommended, 2),
                            confidence=confidence
                        )
                        opportunities.append(opportunity)

        return opportunities

    def _get_sharp_odds(self, event: AggregatedEvent) -> Optional[Dict[str, Dict[str, float]]]:
        """Get odds from sharp bookmaker."""
        for sharp_book in self.sharp_books:
            if sharp_book in event.bookmaker_odds:
                return event.bookmaker_odds[sharp_book]
        return None

    def _calculate_true_probabilities(
        self,
        sharp_odds: Dict[str, Dict[str, float]]
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate true probabilities by removing margin from sharp odds.
        """
        true_probs = {}

        for market_type, selections in sharp_odds.items():
            if not selections:
                continue

            # Get odds values
            odds_list = list(selections.values())
            selection_names = list(selections.keys())

            # Remove margin
            fair_odds = OddsConverter.get_true_odds(odds_list, self.margin_method)

            # Convert to probabilities
            true_probs[market_type] = {}
            for name, fair_odd in zip(selection_names, fair_odds):
                prob = OddsConverter.decimal_to_probability(fair_odd)
                true_probs[market_type][name] = prob

        return true_probs

    def _calculate_ev_percentage(self, true_prob: float, odds: float) -> float:
        """Calculate EV as percentage of stake."""
        return ProbabilityUtils.calculate_ev_percentage(true_prob, odds)

    def _calculate_edge(self, true_prob: float, odds: float) -> float:
        """Calculate edge percentage."""
        return ProbabilityUtils.calculate_edge(true_prob, odds)

    def _determine_confidence(self, ev_pct: float, edge: float, num_books: int) -> str:
        """Determine confidence level of opportunity."""
        # Higher EV and edge = higher confidence
        # More bookmakers with data = higher confidence

        score = 0

        if ev_pct >= 5:
            score += 3
        elif ev_pct >= 3:
            score += 2
        else:
            score += 1

        if edge >= 10:
            score += 2
        elif edge >= 5:
            score += 1

        if num_books >= 4:
            score += 2
        elif num_books >= 3:
            score += 1

        if score >= 6:
            return 'high'
        elif score >= 4:
            return 'medium'
        else:
            return 'low'

    def calculate_ev_for_bet(
        self,
        offered_odds: float,
        sharp_odds: float,
        all_sharp_odds: List[float]
    ) -> dict:
        """
        Calculate EV for a specific bet.

        Args:
            offered_odds: Odds being offered by soft book
            sharp_odds: Sharp book odds for same selection
            all_sharp_odds: All outcomes' odds from sharp book

        Returns:
            Dict with EV calculations
        """
        # Calculate true probability
        fair_odds = OddsConverter.get_true_odds(all_sharp_odds, self.margin_method)

        # Find fair odds for our selection (assume it's the first)
        idx = all_sharp_odds.index(sharp_odds) if sharp_odds in all_sharp_odds else 0
        fair_odd = fair_odds[idx]

        true_prob = OddsConverter.decimal_to_probability(fair_odd)
        ev_pct = self._calculate_ev_percentage(true_prob, offered_odds)
        edge = self._calculate_edge(true_prob, offered_odds)
        kelly = ProbabilityUtils.fractional_kelly(true_prob, offered_odds, self.kelly_fraction)

        return {
            'true_probability': round(true_prob, 4),
            'fair_odds': round(fair_odd, 3),
            'ev_percentage': round(ev_pct, 2),
            'edge': round(edge, 2),
            'kelly_fraction': round(kelly, 4),
            'recommended_stake': round(min(kelly, self.max_bet_pct) * self.bankroll, 2),
            'is_positive_ev': ev_pct > 0
        }

    def update_bankroll(self, new_bankroll: float):
        """Update bankroll for stake calculations."""
        self.bankroll = new_bankroll

    def get_summary(self, opportunities: List[EVOpportunity]) -> dict:
        """Get summary statistics for opportunities."""
        if not opportunities:
            return {
                'total_opportunities': 0,
                'avg_ev': 0,
                'max_ev': 0,
                'total_recommended_stake': 0,
                'by_bookmaker': {},
                'by_sport': {},
                'by_confidence': {'high': 0, 'medium': 0, 'low': 0}
            }

        by_book = {}
        by_sport = {}
        by_conf = {'high': 0, 'medium': 0, 'low': 0}

        for opp in opportunities:
            by_book[opp.bookmaker] = by_book.get(opp.bookmaker, 0) + 1
            by_sport[opp.event.sport] = by_sport.get(opp.event.sport, 0) + 1
            by_conf[opp.confidence] += 1

        return {
            'total_opportunities': len(opportunities),
            'avg_ev': round(sum(o.ev_percentage for o in opportunities) / len(opportunities), 2),
            'max_ev': round(max(o.ev_percentage for o in opportunities), 2),
            'total_recommended_stake': round(sum(o.recommended_stake for o in opportunities), 2),
            'by_bookmaker': by_book,
            'by_sport': by_sport,
            'by_confidence': by_conf
        }
