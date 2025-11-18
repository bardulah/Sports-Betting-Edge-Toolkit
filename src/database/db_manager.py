"""
Database Manager
================

Handles all database operations for the sports betting toolkit.
"""

import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from sqlalchemy import create_engine, func, and_, or_, desc
from sqlalchemy.orm import sessionmaker, Session
import pandas as pd

from .models import (
    Base, Bookmaker, Event, Odds, Bet, BankrollHistory,
    EVOpportunity, ArbitrageOpportunity, CLVRecord, BonusTracker,
    OddsHistory, Settings
)


class DatabaseManager:
    """
    Manager class for all database operations.
    """

    def __init__(self, db_path: str = "data/betting_edge.db"):
        """Initialize database connection."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else '.', exist_ok=True)

        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Create tables
        Base.metadata.create_all(self.engine)

        # Initialize default bookmakers
        self._init_default_bookmakers()

    @contextmanager
    def get_session(self):
        """Context manager for database sessions."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def _init_default_bookmakers(self):
        """Initialize default bookmakers if not present."""
        default_bookmakers = [
            {"name": "Tipsport", "code": "tipsport", "country": "Slovakia", "is_sharp": False, "margin_estimate": 0.06},
            {"name": "Fortuna", "code": "fortuna", "country": "Slovakia", "is_sharp": False, "margin_estimate": 0.055},
            {"name": "Niké", "code": "nike", "country": "Slovakia", "is_sharp": False, "margin_estimate": 0.058},
            {"name": "DOXXbet", "code": "doxxbet", "country": "Slovakia", "is_sharp": False, "margin_estimate": 0.05},
            {"name": "Pinnacle", "code": "pinnacle", "country": "International", "is_sharp": True, "margin_estimate": 0.02},
            {"name": "Bet365", "code": "bet365", "country": "International", "is_sharp": False, "margin_estimate": 0.04},
        ]

        with self.get_session() as session:
            for book_data in default_bookmakers:
                existing = session.query(Bookmaker).filter_by(code=book_data["code"]).first()
                if not existing:
                    bookmaker = Bookmaker(**book_data)
                    session.add(bookmaker)

    # ==================== BOOKMAKER OPERATIONS ====================

    def get_bookmaker(self, code: str) -> Optional[Bookmaker]:
        """Get bookmaker by code."""
        with self.get_session() as session:
            return session.query(Bookmaker).filter_by(code=code).first()

    def get_all_bookmakers(self, active_only: bool = True) -> List[Bookmaker]:
        """Get all bookmakers."""
        with self.get_session() as session:
            query = session.query(Bookmaker)
            if active_only:
                query = query.filter_by(is_active=True)
            return query.all()

    def get_sharp_bookmakers(self) -> List[Bookmaker]:
        """Get sharp bookmakers."""
        with self.get_session() as session:
            return session.query(Bookmaker).filter_by(is_sharp=True, is_active=True).all()

    # ==================== EVENT OPERATIONS ====================

    def add_event(self, event_data: dict) -> int:
        """Add or update an event."""
        with self.get_session() as session:
            # Check if event exists
            existing = session.query(Event).filter(
                and_(
                    Event.home_team == event_data['home_team'],
                    Event.away_team == event_data['away_team'],
                    Event.start_time == event_data['start_time']
                )
            ).first()

            if existing:
                for key, value in event_data.items():
                    setattr(existing, key, value)
                return existing.id
            else:
                event = Event(**event_data)
                session.add(event)
                session.flush()
                return event.id

    def get_event(self, event_id: int) -> Optional[Event]:
        """Get event by ID."""
        with self.get_session() as session:
            return session.query(Event).get(event_id)

    def get_upcoming_events(self, sport: str = None, hours: int = 24) -> List[Event]:
        """Get upcoming events within specified hours."""
        with self.get_session() as session:
            cutoff = datetime.now() + timedelta(hours=hours)
            query = session.query(Event).filter(
                and_(
                    Event.start_time > datetime.now(),
                    Event.start_time < cutoff
                )
            )
            if sport:
                query = query.filter(Event.sport == sport)
            return query.order_by(Event.start_time).all()

    def find_event(self, home_team: str, away_team: str, start_time: datetime) -> Optional[Event]:
        """Find event by teams and time."""
        with self.get_session() as session:
            return session.query(Event).filter(
                and_(
                    Event.home_team == home_team,
                    Event.away_team == away_team,
                    Event.start_time == start_time
                )
            ).first()

    # ==================== ODDS OPERATIONS ====================

    def add_odds(self, odds_data: dict) -> int:
        """Add odds record."""
        with self.get_session() as session:
            odds = Odds(**odds_data)
            session.add(odds)
            session.flush()
            return odds.id

    def add_odds_batch(self, odds_list: List[dict]):
        """Add multiple odds records."""
        with self.get_session() as session:
            for odds_data in odds_list:
                odds = Odds(**odds_data)
                session.add(odds)

    def get_current_odds(self, event_id: int) -> List[Odds]:
        """Get latest odds for an event."""
        with self.get_session() as session:
            # Get latest odds for each bookmaker/market/selection combination
            subquery = session.query(
                Odds.bookmaker_id,
                Odds.market_type,
                Odds.selection,
                func.max(Odds.timestamp).label('max_time')
            ).filter(Odds.event_id == event_id).group_by(
                Odds.bookmaker_id, Odds.market_type, Odds.selection
            ).subquery()

            return session.query(Odds).join(
                subquery,
                and_(
                    Odds.bookmaker_id == subquery.c.bookmaker_id,
                    Odds.market_type == subquery.c.market_type,
                    Odds.selection == subquery.c.selection,
                    Odds.timestamp == subquery.c.max_time
                )
            ).filter(Odds.event_id == event_id).all()

    def get_odds_comparison(self, event_id: int, market_type: str) -> pd.DataFrame:
        """Get odds comparison across bookmakers for a market."""
        with self.get_session() as session:
            odds = session.query(Odds).join(Bookmaker).filter(
                and_(
                    Odds.event_id == event_id,
                    Odds.market_type == market_type
                )
            ).all()

            data = []
            for o in odds:
                data.append({
                    'bookmaker': o.bookmaker.name,
                    'selection': o.selection,
                    'odds': o.odds_value,
                    'timestamp': o.timestamp
                })

            return pd.DataFrame(data)

    # ==================== BET OPERATIONS ====================

    def add_bet(self, bet_data: dict) -> int:
        """Add a new bet."""
        with self.get_session() as session:
            # Calculate potential return
            if 'potential_return' not in bet_data:
                bet_data['potential_return'] = bet_data['stake'] * bet_data['odds']

            bet = Bet(**bet_data)
            session.add(bet)
            session.flush()

            # Record bankroll change
            self._record_bet_bankroll_change(session, bet)

            return bet.id

    def update_bet(self, bet_id: int, updates: dict):
        """Update a bet."""
        with self.get_session() as session:
            bet = session.query(Bet).get(bet_id)
            if bet:
                for key, value in updates.items():
                    setattr(bet, key, value)

    def settle_bet(self, bet_id: int, status: str, actual_return: float = 0):
        """Settle a bet with result."""
        with self.get_session() as session:
            bet = session.query(Bet).get(bet_id)
            if bet:
                bet.status = status
                bet.actual_return = actual_return
                bet.profit_loss = actual_return - bet.stake
                bet.settled_at = datetime.now()

                # Record bankroll change
                self._record_bankroll_change(
                    session,
                    bet.profit_loss,
                    f'bet_{status}',
                    bet_id=bet_id
                )

    def get_bet(self, bet_id: int) -> Optional[Bet]:
        """Get bet by ID."""
        with self.get_session() as session:
            return session.query(Bet).get(bet_id)

    def get_pending_bets(self) -> List[Bet]:
        """Get all pending bets."""
        with self.get_session() as session:
            return session.query(Bet).filter_by(status='pending').all()

    def get_bets(
        self,
        status: str = None,
        bookmaker: str = None,
        sport: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        limit: int = 100
    ) -> List[Bet]:
        """Get bets with filters."""
        with self.get_session() as session:
            query = session.query(Bet)

            if status:
                query = query.filter(Bet.status == status)
            if bookmaker:
                query = query.join(Bookmaker).filter(Bookmaker.code == bookmaker)
            if sport:
                query = query.filter(Bet.sport == sport)
            if start_date:
                query = query.filter(Bet.placed_at >= start_date)
            if end_date:
                query = query.filter(Bet.placed_at <= end_date)

            return query.order_by(desc(Bet.placed_at)).limit(limit).all()

    def get_betting_stats(
        self,
        start_date: datetime = None,
        end_date: datetime = None,
        bookmaker: str = None,
        sport: str = None
    ) -> dict:
        """Calculate betting statistics."""
        with self.get_session() as session:
            query = session.query(Bet).filter(Bet.status != 'pending')

            if start_date:
                query = query.filter(Bet.placed_at >= start_date)
            if end_date:
                query = query.filter(Bet.placed_at <= end_date)
            if bookmaker:
                query = query.join(Bookmaker).filter(Bookmaker.code == bookmaker)
            if sport:
                query = query.filter(Bet.sport == sport)

            bets = query.all()

            if not bets:
                return {
                    'total_bets': 0,
                    'wins': 0,
                    'losses': 0,
                    'win_rate': 0,
                    'total_staked': 0,
                    'total_returned': 0,
                    'profit_loss': 0,
                    'roi': 0,
                    'avg_odds': 0,
                    'avg_stake': 0,
                    'avg_clv': 0
                }

            wins = len([b for b in bets if b.status == 'won'])
            losses = len([b for b in bets if b.status == 'lost'])
            total_staked = sum(b.stake for b in bets)
            total_returned = sum(b.actual_return for b in bets)
            profit_loss = sum(b.profit_loss for b in bets)

            clv_values = [b.clv for b in bets if b.clv is not None]

            return {
                'total_bets': len(bets),
                'wins': wins,
                'losses': losses,
                'win_rate': round((wins / len(bets)) * 100, 2) if bets else 0,
                'total_staked': round(total_staked, 2),
                'total_returned': round(total_returned, 2),
                'profit_loss': round(profit_loss, 2),
                'roi': round((profit_loss / total_staked) * 100, 2) if total_staked > 0 else 0,
                'avg_odds': round(sum(b.odds for b in bets) / len(bets), 3) if bets else 0,
                'avg_stake': round(total_staked / len(bets), 2) if bets else 0,
                'avg_clv': round(sum(clv_values) / len(clv_values), 2) if clv_values else 0
            }

    def import_bets(self, bets_data: List[dict]) -> int:
        """Import multiple bets from external source."""
        count = 0
        with self.get_session() as session:
            for bet_data in bets_data:
                bet_data['imported'] = True
                bet = Bet(**bet_data)
                session.add(bet)
                count += 1
        return count

    # ==================== BANKROLL OPERATIONS ====================

    def _record_bet_bankroll_change(self, session: Session, bet: Bet):
        """Record bankroll change for bet placement."""
        # This is handled within transaction
        pass

    def _record_bankroll_change(
        self,
        session: Session,
        change: float,
        reason: str,
        bet_id: int = None,
        notes: str = None
    ):
        """Record a bankroll change."""
        # Get current bankroll
        latest = session.query(BankrollHistory).order_by(
            desc(BankrollHistory.timestamp)
        ).first()

        current = latest.bankroll if latest else 1000  # Default starting bankroll

        record = BankrollHistory(
            bankroll=current + change,
            change=change,
            change_reason=reason,
            bet_id=bet_id,
            notes=notes
        )
        session.add(record)

    def record_deposit(self, amount: float, notes: str = None):
        """Record a deposit."""
        with self.get_session() as session:
            self._record_bankroll_change(session, amount, 'deposit', notes=notes)

    def record_withdrawal(self, amount: float, notes: str = None):
        """Record a withdrawal."""
        with self.get_session() as session:
            self._record_bankroll_change(session, -amount, 'withdrawal', notes=notes)

    def get_current_bankroll(self) -> float:
        """Get current bankroll."""
        with self.get_session() as session:
            latest = session.query(BankrollHistory).order_by(
                desc(BankrollHistory.timestamp)
            ).first()
            return latest.bankroll if latest else 1000

    def get_bankroll_history(
        self,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> pd.DataFrame:
        """Get bankroll history as DataFrame."""
        with self.get_session() as session:
            query = session.query(BankrollHistory)

            if start_date:
                query = query.filter(BankrollHistory.timestamp >= start_date)
            if end_date:
                query = query.filter(BankrollHistory.timestamp <= end_date)

            records = query.order_by(BankrollHistory.timestamp).all()

            data = [{
                'timestamp': r.timestamp,
                'bankroll': r.bankroll,
                'change': r.change,
                'reason': r.change_reason
            } for r in records]

            return pd.DataFrame(data)

    def set_initial_bankroll(self, amount: float):
        """Set initial bankroll."""
        with self.get_session() as session:
            # Clear existing history
            session.query(BankrollHistory).delete()

            # Add initial record
            record = BankrollHistory(
                bankroll=amount,
                change=amount,
                change_reason='initial'
            )
            session.add(record)

    # ==================== EV OPPORTUNITY OPERATIONS ====================

    def add_ev_opportunity(self, ev_data: dict) -> int:
        """Add EV opportunity."""
        with self.get_session() as session:
            opportunity = EVOpportunity(**ev_data)
            session.add(opportunity)
            session.flush()
            return opportunity.id

    def get_active_ev_opportunities(self, min_ev: float = 0) -> List[EVOpportunity]:
        """Get active EV opportunities."""
        with self.get_session() as session:
            return session.query(EVOpportunity).filter(
                and_(
                    EVOpportunity.is_active == True,
                    EVOpportunity.ev_percentage >= min_ev
                )
            ).order_by(desc(EVOpportunity.ev_percentage)).all()

    def deactivate_old_ev_opportunities(self, hours: int = 1):
        """Deactivate old EV opportunities."""
        with self.get_session() as session:
            cutoff = datetime.now() - timedelta(hours=hours)
            session.query(EVOpportunity).filter(
                EVOpportunity.detected_at < cutoff
            ).update({'is_active': False})

    # ==================== ARBITRAGE OPERATIONS ====================

    def add_arbitrage_opportunity(self, arb_data: dict) -> int:
        """Add arbitrage opportunity."""
        with self.get_session() as session:
            opportunity = ArbitrageOpportunity(**arb_data)
            session.add(opportunity)
            session.flush()
            return opportunity.id

    def get_active_arbitrage_opportunities(self, min_profit: float = 0) -> List[ArbitrageOpportunity]:
        """Get active arbitrage opportunities."""
        with self.get_session() as session:
            return session.query(ArbitrageOpportunity).filter(
                and_(
                    ArbitrageOpportunity.is_active == True,
                    ArbitrageOpportunity.profit_percentage >= min_profit
                )
            ).order_by(desc(ArbitrageOpportunity.profit_percentage)).all()

    # ==================== CLV OPERATIONS ====================

    def add_clv_record(self, clv_data: dict) -> int:
        """Add CLV record."""
        with self.get_session() as session:
            record = CLVRecord(**clv_data)
            session.add(record)
            session.flush()
            return record.id

    def get_clv_stats(self, start_date: datetime = None) -> dict:
        """Get CLV statistics."""
        with self.get_session() as session:
            query = session.query(CLVRecord)

            if start_date:
                query = query.filter(CLVRecord.recorded_at >= start_date)

            records = query.all()

            if not records:
                return {'avg_clv': 0, 'positive_clv_rate': 0, 'total_records': 0}

            clv_values = [r.clv_vs_close for r in records if r.clv_vs_close is not None]
            positive = len([c for c in clv_values if c > 0])

            return {
                'avg_clv': round(sum(clv_values) / len(clv_values), 2) if clv_values else 0,
                'positive_clv_rate': round((positive / len(clv_values)) * 100, 2) if clv_values else 0,
                'total_records': len(records)
            }

    # ==================== BONUS TRACKER OPERATIONS ====================

    def add_bonus(self, bonus_data: dict) -> int:
        """Add bonus to track."""
        with self.get_session() as session:
            # Calculate amount required
            if 'amount_required' not in bonus_data:
                bonus_data['amount_required'] = (
                    bonus_data['bonus_amount'] * bonus_data.get('wagering_requirement', 1)
                )

            bonus = BonusTracker(**bonus_data)
            session.add(bonus)
            session.flush()
            return bonus.id

    def update_bonus_progress(self, bonus_id: int, wagered: float):
        """Update bonus wagering progress."""
        with self.get_session() as session:
            bonus = session.query(BonusTracker).get(bonus_id)
            if bonus:
                bonus.amount_wagered += wagered
                bonus.progress_percentage = (
                    bonus.amount_wagered / bonus.amount_required * 100
                    if bonus.amount_required > 0 else 100
                )

                if bonus.amount_wagered >= bonus.amount_required:
                    bonus.status = 'completed'
                    bonus.completed_at = datetime.now()

    def get_active_bonuses(self) -> List[BonusTracker]:
        """Get active bonuses."""
        with self.get_session() as session:
            return session.query(BonusTracker).filter_by(status='active').all()

    # ==================== SETTINGS OPERATIONS ====================

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        with self.get_session() as session:
            setting = session.query(Settings).filter_by(key=key).first()
            if not setting:
                return default

            if setting.value_type == 'int':
                return int(setting.value)
            elif setting.value_type == 'float':
                return float(setting.value)
            elif setting.value_type == 'bool':
                return setting.value.lower() == 'true'
            elif setting.value_type == 'json':
                import json
                return json.loads(setting.value)
            else:
                return setting.value

    def set_setting(self, key: str, value: Any):
        """Set a setting value."""
        with self.get_session() as session:
            setting = session.query(Settings).filter_by(key=key).first()

            value_type = 'string'
            if isinstance(value, bool):
                value_type = 'bool'
                value = str(value)
            elif isinstance(value, int):
                value_type = 'int'
                value = str(value)
            elif isinstance(value, float):
                value_type = 'float'
                value = str(value)
            elif isinstance(value, (dict, list)):
                import json
                value_type = 'json'
                value = json.dumps(value)
            else:
                value = str(value)

            if setting:
                setting.value = value
                setting.value_type = value_type
            else:
                setting = Settings(key=key, value=value, value_type=value_type)
                session.add(setting)

    # ==================== EXPORT OPERATIONS ====================

    def export_bets_to_csv(self, filepath: str, **filters):
        """Export bets to CSV."""
        bets = self.get_bets(**filters)

        data = [{
            'id': b.id,
            'placed_at': b.placed_at,
            'bookmaker': b.bookmaker.name if b.bookmaker else '',
            'sport': b.sport,
            'league': b.league,
            'event': b.event_name,
            'selection': b.selection,
            'odds': b.odds,
            'stake': b.stake,
            'status': b.status,
            'profit_loss': b.profit_loss,
            'clv': b.clv,
            'ev_at_placement': b.ev_at_placement
        } for b in bets]

        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)
        return len(data)

    def get_stats_by_league(self) -> pd.DataFrame:
        """Get betting stats grouped by league."""
        with self.get_session() as session:
            bets = session.query(Bet).filter(Bet.status != 'pending').all()

            league_stats = {}
            for bet in bets:
                league = bet.league or 'Unknown'
                if league not in league_stats:
                    league_stats[league] = {
                        'bets': 0, 'wins': 0, 'staked': 0, 'profit': 0
                    }

                league_stats[league]['bets'] += 1
                if bet.status == 'won':
                    league_stats[league]['wins'] += 1
                league_stats[league]['staked'] += bet.stake
                league_stats[league]['profit'] += bet.profit_loss

            data = []
            for league, stats in league_stats.items():
                data.append({
                    'league': league,
                    'total_bets': stats['bets'],
                    'wins': stats['wins'],
                    'win_rate': round((stats['wins'] / stats['bets']) * 100, 2) if stats['bets'] > 0 else 0,
                    'total_staked': round(stats['staked'], 2),
                    'profit_loss': round(stats['profit'], 2),
                    'roi': round((stats['profit'] / stats['staked']) * 100, 2) if stats['staked'] > 0 else 0
                })

            return pd.DataFrame(data).sort_values('profit_loss', ascending=False)
