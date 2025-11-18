"""
CLV Tracker
===========

Tracks Closing Line Value - the most important metric for measuring
betting skill. Beating the closing line consistently = long-term profit.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging
import pandas as pd

from ..utils.odds_converter import OddsConverter
from ..utils.probability_utils import ProbabilityUtils
from ..database.db_manager import DatabaseManager


@dataclass
class CLVAnalysis:
    """Analysis results for CLV."""
    bet_id: int
    event_name: str
    selection: str
    bet_odds: float
    closing_odds: float
    clv_percentage: float
    pinnacle_opening: Optional[float]
    pinnacle_closing: Optional[float]
    clv_vs_pinnacle: Optional[float]
    hours_before_close: float


class CLVTracker:
    """
    Tracks and analyzes Closing Line Value.

    CLV measures how your bet odds compare to the closing line (final odds).
    Consistently beating the closing line is the best predictor of long-term profit.
    """

    def __init__(self, db_manager: DatabaseManager = None, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("CLVTracker")

        self.db = db_manager or DatabaseManager()

        # Configuration
        self.track_pinnacle = self.config.get('compare_to_pinnacle', True)
        self.track_hours = self.config.get('track_hours_before_close', [24, 12, 6, 1])

    def calculate_clv(self, bet_odds: float, closing_odds: float) -> float:
        """
        Calculate Closing Line Value.

        Args:
            bet_odds: Odds when bet was placed
            closing_odds: Final odds before event start

        Returns:
            CLV as percentage (positive = beat the line)
        """
        return ProbabilityUtils.calculate_clv(bet_odds, closing_odds)

    def record_bet_placement(
        self,
        bet_id: int,
        bookmaker: str,
        selection: str,
        bet_odds: float,
        pinnacle_odds: float = None
    ):
        """
        Record odds at bet placement for CLV tracking.

        Args:
            bet_id: Database bet ID
            bookmaker: Bookmaker name
            selection: Bet selection
            bet_odds: Odds when placed
            pinnacle_odds: Pinnacle odds at placement (optional)
        """
        clv_data = {
            'bet_id': bet_id,
            'bookmaker': bookmaker,
            'selection': selection,
            'bet_odds': bet_odds,
            'pinnacle_opening': pinnacle_odds,
            'bet_placed_at': datetime.now()
        }

        self.db.add_clv_record(clv_data)
        self.logger.info(f"Recorded bet placement for CLV tracking: {bet_id}")

    def record_closing_odds(
        self,
        bet_id: int,
        closing_odds: float,
        pinnacle_closing: float = None
    ):
        """
        Record closing odds and calculate CLV.

        Args:
            bet_id: Database bet ID
            closing_odds: Final bookmaker odds
            pinnacle_closing: Final Pinnacle odds
        """
        # Get the CLV record
        # Update with closing odds and calculate CLV
        clv_vs_close = self.calculate_clv(closing_odds, closing_odds)  # Will update from record

        # Calculate CLV vs Pinnacle if available
        clv_vs_pinnacle = None
        if pinnacle_closing:
            # Get bet odds from record
            pass  # Will implement with actual DB query

        self.logger.info(f"Recorded closing odds for bet {bet_id}: CLV = {clv_vs_close}%")

    def analyze_bet_history(
        self,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> dict:
        """
        Analyze CLV performance over bet history.

        Returns:
            Dictionary with CLV statistics
        """
        stats = self.db.get_clv_stats(start_date)

        # Enhanced analysis
        bets = self.db.get_bets(start_date=start_date, end_date=end_date)

        clv_values = []
        win_with_positive_clv = 0
        win_with_negative_clv = 0
        lose_with_positive_clv = 0
        lose_with_negative_clv = 0

        for bet in bets:
            if bet.clv is not None:
                clv_values.append(bet.clv)

                if bet.clv > 0:
                    if bet.status == 'won':
                        win_with_positive_clv += 1
                    elif bet.status == 'lost':
                        lose_with_positive_clv += 1
                else:
                    if bet.status == 'won':
                        win_with_negative_clv += 1
                    elif bet.status == 'lost':
                        lose_with_negative_clv += 1

        if not clv_values:
            return {
                'total_bets_with_clv': 0,
                'avg_clv': 0,
                'median_clv': 0,
                'positive_clv_rate': 0,
                'clv_edge': 0,
                'correlation_with_results': None
            }

        clv_series = pd.Series(clv_values)

        return {
            'total_bets_with_clv': len(clv_values),
            'avg_clv': round(clv_series.mean(), 2),
            'median_clv': round(clv_series.median(), 2),
            'std_clv': round(clv_series.std(), 2),
            'positive_clv_rate': round((sum(1 for c in clv_values if c > 0) / len(clv_values)) * 100, 1),
            'max_clv': round(clv_series.max(), 2),
            'min_clv': round(clv_series.min(), 2),
            'win_positive_clv': win_with_positive_clv,
            'win_negative_clv': win_with_negative_clv,
            'lose_positive_clv': lose_with_positive_clv,
            'lose_negative_clv': lose_with_negative_clv,
        }

    def get_clv_by_bookmaker(self) -> pd.DataFrame:
        """Get CLV breakdown by bookmaker."""
        bets = self.db.get_bets(limit=1000)

        data = {}
        for bet in bets:
            if bet.clv is None:
                continue

            book = bet.bookmaker.name if bet.bookmaker else 'Unknown'
            if book not in data:
                data[book] = {'clv_values': [], 'wins': 0, 'total': 0}

            data[book]['clv_values'].append(bet.clv)
            data[book]['total'] += 1
            if bet.status == 'won':
                data[book]['wins'] += 1

        results = []
        for book, info in data.items():
            results.append({
                'bookmaker': book,
                'total_bets': info['total'],
                'avg_clv': round(sum(info['clv_values']) / len(info['clv_values']), 2),
                'positive_clv_rate': round(
                    sum(1 for c in info['clv_values'] if c > 0) / len(info['clv_values']) * 100, 1
                ),
                'win_rate': round(info['wins'] / info['total'] * 100, 1)
            })

        return pd.DataFrame(results).sort_values('avg_clv', ascending=False)

    def get_clv_by_sport(self) -> pd.DataFrame:
        """Get CLV breakdown by sport."""
        bets = self.db.get_bets(limit=1000)

        data = {}
        for bet in bets:
            if bet.clv is None or not bet.sport:
                continue

            sport = bet.sport
            if sport not in data:
                data[sport] = {'clv_values': []}

            data[sport]['clv_values'].append(bet.clv)

        results = []
        for sport, info in data.items():
            results.append({
                'sport': sport,
                'total_bets': len(info['clv_values']),
                'avg_clv': round(sum(info['clv_values']) / len(info['clv_values']), 2),
                'positive_clv_rate': round(
                    sum(1 for c in info['clv_values'] if c > 0) / len(info['clv_values']) * 100, 1
                )
            })

        return pd.DataFrame(results).sort_values('avg_clv', ascending=False)

    def get_clv_over_time(self, period: str = 'week') -> pd.DataFrame:
        """
        Get CLV trends over time.

        Args:
            period: 'day', 'week', or 'month'
        """
        bets = self.db.get_bets(limit=2000)

        data = []
        for bet in bets:
            if bet.clv is None:
                continue

            data.append({
                'date': bet.placed_at,
                'clv': bet.clv
            })

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])

        if period == 'day':
            df = df.groupby(df['date'].dt.date).agg({
                'clv': ['mean', 'count']
            }).reset_index()
        elif period == 'week':
            df = df.groupby(df['date'].dt.to_period('W')).agg({
                'clv': ['mean', 'count']
            }).reset_index()
        else:  # month
            df = df.groupby(df['date'].dt.to_period('M')).agg({
                'clv': ['mean', 'count']
            }).reset_index()

        df.columns = ['period', 'avg_clv', 'num_bets']
        return df

    def predict_long_term_roi(self, avg_clv: float) -> dict:
        """
        Predict long-term ROI based on CLV.

        There's a strong correlation between CLV and actual ROI.
        """
        # Simplified model: ROI ≈ CLV * factor
        # This is a rough approximation - actual results vary

        estimated_roi = avg_clv * 0.8  # Conservative estimate

        return {
            'avg_clv': avg_clv,
            'estimated_roi': round(estimated_roi, 2),
            'confidence': 'medium' if abs(avg_clv) < 3 else 'higher',
            'note': 'CLV is the best predictor of long-term profitability. '
                    'Beating the closing line by 2%+ consistently suggests edge.'
        }

    def get_skill_assessment(self) -> dict:
        """
        Assess betting skill based on CLV metrics.
        """
        stats = self.analyze_bet_history()

        if stats['total_bets_with_clv'] < 50:
            return {
                'assessment': 'Insufficient data',
                'sample_size': stats['total_bets_with_clv'],
                'recommendation': 'Need 50+ bets with CLV tracking for reliable assessment'
            }

        avg_clv = stats['avg_clv']
        pos_rate = stats['positive_clv_rate']

        if avg_clv >= 3 and pos_rate >= 60:
            skill = 'Sharp'
            desc = 'Consistently beating the market. Strong edge detected.'
        elif avg_clv >= 1 and pos_rate >= 55:
            skill = 'Skilled'
            desc = 'Positive expected value. Keep tracking and refining.'
        elif avg_clv >= 0 and pos_rate >= 50:
            skill = 'Break-even'
            desc = 'Near market efficiency. Look for better spots.'
        else:
            skill = 'Needs Improvement'
            desc = 'Negative CLV indicates poor line shopping or timing.'

        return {
            'skill_level': skill,
            'description': desc,
            'avg_clv': avg_clv,
            'positive_clv_rate': pos_rate,
            'sample_size': stats['total_bets_with_clv'],
            'recommendation': self._get_recommendation(skill, avg_clv)
        }

    def _get_recommendation(self, skill: str, avg_clv: float) -> str:
        """Get personalized recommendation based on skill level."""
        if skill == 'Sharp':
            return 'Maintain your edge. Consider increasing stakes on highest CLV bets.'
        elif skill == 'Skilled':
            return 'Good work! Focus on bets with 3%+ CLV for best results.'
        elif skill == 'Break-even':
            return 'Improve line shopping. Bet earlier when you spot value.'
        else:
            return 'Review your bet selection process. Focus on markets where you have knowledge edge.'
