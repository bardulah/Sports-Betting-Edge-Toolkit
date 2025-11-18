"""
Database Models
===============

SQLAlchemy models for the sports betting edge toolkit.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, Float, String, DateTime, Boolean,
    ForeignKey, Text, Enum, JSON, Index
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import enum

Base = declarative_base()


class BetStatus(enum.Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    VOID = "void"
    CASHOUT = "cashout"
    HALF_WON = "half_won"
    HALF_LOST = "half_lost"


class Sport(enum.Enum):
    FOOTBALL = "football"
    HOCKEY = "hockey"
    TENNIS = "tennis"
    BASKETBALL = "basketball"
    OTHER = "other"


class MarketType(enum.Enum):
    MONEYLINE = "moneyline"
    SPREAD = "spread"
    TOTAL = "total"
    BOTH_TO_SCORE = "btts"
    DOUBLE_CHANCE = "double_chance"
    DRAW_NO_BET = "draw_no_bet"
    ASIAN_HANDICAP = "asian_handicap"
    CORRECT_SCORE = "correct_score"
    OTHER = "other"


class Bookmaker(Base):
    __tablename__ = 'bookmakers'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    country = Column(String(50))
    is_sharp = Column(Boolean, default=False)
    base_url = Column(String(255))
    margin_estimate = Column(Float, default=0.05)
    max_payout = Column(Float)
    currency = Column(String(10), default='EUR')
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    odds = relationship("Odds", back_populates="bookmaker")
    bets = relationship("Bet", back_populates="bookmaker")


class Event(Base):
    __tablename__ = 'events'

    id = Column(Integer, primary_key=True)
    external_id = Column(String(100))  # ID from bookmaker
    sport = Column(String(50), nullable=False)
    league = Column(String(200))
    home_team = Column(String(200), nullable=False)
    away_team = Column(String(200), nullable=False)
    start_time = Column(DateTime, nullable=False)
    is_live = Column(Boolean, default=False)
    status = Column(String(50), default='scheduled')
    home_score = Column(Integer)
    away_score = Column(Integer)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    odds = relationship("Odds", back_populates="event")
    bets = relationship("Bet", back_populates="event")
    clv_records = relationship("CLVRecord", back_populates="event")

    __table_args__ = (
        Index('idx_event_teams_time', 'home_team', 'away_team', 'start_time'),
        Index('idx_event_sport_league', 'sport', 'league'),
    )


class Odds(Base):
    __tablename__ = 'odds'

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    bookmaker_id = Column(Integer, ForeignKey('bookmakers.id'), nullable=False)
    market_type = Column(String(50), nullable=False)
    selection = Column(String(100), nullable=False)  # e.g., "home", "away", "draw", "over 2.5"
    odds_value = Column(Float, nullable=False)
    line = Column(Float)  # For spreads/totals
    is_live = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=func.now())

    # Relationships
    event = relationship("Event", back_populates="odds")
    bookmaker = relationship("Bookmaker", back_populates="odds")

    __table_args__ = (
        Index('idx_odds_event_book_market', 'event_id', 'bookmaker_id', 'market_type'),
        Index('idx_odds_timestamp', 'timestamp'),
    )


class Bet(Base):
    __tablename__ = 'bets'

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))
    bookmaker_id = Column(Integer, ForeignKey('bookmakers.id'), nullable=False)

    # Bet details
    sport = Column(String(50))
    league = Column(String(200))
    event_name = Column(String(400))
    market_type = Column(String(50))
    selection = Column(String(200), nullable=False)
    odds = Column(Float, nullable=False)
    stake = Column(Float, nullable=False)
    potential_return = Column(Float)

    # Bet placement info
    placed_at = Column(DateTime, default=func.now())
    settled_at = Column(DateTime)
    status = Column(String(20), default='pending')

    # Results
    profit_loss = Column(Float, default=0)
    actual_return = Column(Float, default=0)

    # Analytics
    ev_at_placement = Column(Float)  # EV when bet was placed
    closing_odds = Column(Float)  # Odds at close
    clv = Column(Float)  # Closing line value
    true_probability = Column(Float)  # Estimated true prob
    kelly_fraction = Column(Float)  # Kelly stake used

    # Metadata
    notes = Column(Text)
    tags = Column(JSON)  # e.g., ["value", "sharp_move", "bonus"]
    is_bonus_bet = Column(Boolean, default=False)
    imported = Column(Boolean, default=False)  # If imported from CSV
    source = Column(String(50))  # 'manual', 'csv_import', 'auto'

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    event = relationship("Event", back_populates="bets")
    bookmaker = relationship("Bookmaker", back_populates="bets")

    __table_args__ = (
        Index('idx_bet_status', 'status'),
        Index('idx_bet_placed_at', 'placed_at'),
        Index('idx_bet_bookmaker_sport', 'bookmaker_id', 'sport'),
    )


class BankrollHistory(Base):
    __tablename__ = 'bankroll_history'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=func.now())
    bankroll = Column(Float, nullable=False)
    change = Column(Float, default=0)
    change_reason = Column(String(100))  # 'bet_win', 'bet_loss', 'deposit', 'withdrawal'
    bet_id = Column(Integer, ForeignKey('bets.id'))
    notes = Column(Text)

    __table_args__ = (
        Index('idx_bankroll_timestamp', 'timestamp'),
    )


class EVOpportunity(Base):
    __tablename__ = 'ev_opportunities'

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))

    # Event info
    sport = Column(String(50))
    league = Column(String(200))
    home_team = Column(String(200))
    away_team = Column(String(200))
    start_time = Column(DateTime)

    # Opportunity details
    bookmaker = Column(String(100), nullable=False)
    market_type = Column(String(50))
    selection = Column(String(200))
    offered_odds = Column(Float, nullable=False)

    # Sharp book comparison
    sharp_book = Column(String(100))
    sharp_odds = Column(Float)
    true_probability = Column(Float)

    # EV calculations
    ev_percentage = Column(Float, nullable=False)
    edge = Column(Float)

    # Recommended bet
    kelly_stake = Column(Float)
    recommended_stake = Column(Float)

    # Status
    detected_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    was_bet = Column(Boolean, default=False)
    notification_sent = Column(Boolean, default=False)

    __table_args__ = (
        Index('idx_ev_active', 'is_active'),
        Index('idx_ev_detected', 'detected_at'),
        Index('idx_ev_percentage', 'ev_percentage'),
    )


class ArbitrageOpportunity(Base):
    __tablename__ = 'arbitrage_opportunities'

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))

    # Event info
    sport = Column(String(50))
    league = Column(String(200))
    home_team = Column(String(200))
    away_team = Column(String(200))
    start_time = Column(DateTime)

    # Arb details
    market_type = Column(String(50))
    profit_percentage = Column(Float, nullable=False)
    total_stake = Column(Float)
    expected_profit = Column(Float)

    # Legs (stored as JSON)
    legs = Column(JSON)  # [{bookmaker, selection, odds, stake, potential_return}]

    # Status
    detected_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    was_bet = Column(Boolean, default=False)
    notification_sent = Column(Boolean, default=False)

    __table_args__ = (
        Index('idx_arb_active', 'is_active'),
        Index('idx_arb_profit', 'profit_percentage'),
    )


class CLVRecord(Base):
    __tablename__ = 'clv_records'

    id = Column(Integer, primary_key=True)
    bet_id = Column(Integer, ForeignKey('bets.id'))
    event_id = Column(Integer, ForeignKey('events.id'))

    # Tracking info
    bookmaker = Column(String(100))
    market_type = Column(String(50))
    selection = Column(String(200))

    # Odds history
    bet_odds = Column(Float, nullable=False)
    closing_odds = Column(Float)
    pinnacle_opening = Column(Float)
    pinnacle_closing = Column(Float)

    # Calculated CLV
    clv_vs_close = Column(Float)  # vs own bookmaker
    clv_vs_pinnacle = Column(Float)  # vs sharp book

    # Timestamps
    bet_placed_at = Column(DateTime)
    odds_closed_at = Column(DateTime)
    recorded_at = Column(DateTime, default=func.now())

    # Relationships
    event = relationship("Event", back_populates="clv_records")

    __table_args__ = (
        Index('idx_clv_bet', 'bet_id'),
        Index('idx_clv_recorded', 'recorded_at'),
    )


class BonusTracker(Base):
    __tablename__ = 'bonus_tracker'

    id = Column(Integer, primary_key=True)
    bookmaker = Column(String(100), nullable=False)

    # Bonus details
    bonus_type = Column(String(50))  # 'deposit', 'free_bet', 'cashback'
    bonus_amount = Column(Float, nullable=False)
    wagering_requirement = Column(Float)  # Rollover multiplier
    max_odds = Column(Float)  # Max odds for rollover
    min_odds = Column(Float)  # Min odds for rollover

    # Progress
    amount_wagered = Column(Float, default=0)
    amount_required = Column(Float)
    progress_percentage = Column(Float, default=0)

    # Status
    status = Column(String(20), default='active')  # 'active', 'completed', 'expired', 'forfeited'
    received_at = Column(DateTime)
    expires_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Results
    profit_loss = Column(Float, default=0)
    ev_of_bonus = Column(Float)  # Expected value of bonus

    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_bonus_status', 'status'),
        Index('idx_bonus_bookmaker', 'bookmaker'),
    )


class OddsHistory(Base):
    """Track odds movements over time for CLV analysis"""
    __tablename__ = 'odds_history'

    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))
    bookmaker = Column(String(100), nullable=False)
    market_type = Column(String(50))
    selection = Column(String(200))
    odds_value = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_odds_history_event', 'event_id', 'bookmaker', 'market_type'),
        Index('idx_odds_history_time', 'timestamp'),
    )


class Settings(Base):
    """User settings and preferences"""
    __tablename__ = 'settings'

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text)
    value_type = Column(String(20))  # 'string', 'int', 'float', 'bool', 'json'
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
