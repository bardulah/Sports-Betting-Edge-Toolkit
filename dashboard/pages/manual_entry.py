"""
Manual Entry Page
=================

Fallback for manually entering odds when scrapers fail.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.database.db_manager import DatabaseManager
from src.analyzers.ev_calculator import EVCalculator
from src.analyzers.arbitrage_finder import ArbitrageFinder
from src.utils.odds_converter import OddsConverter


def show_manual_entry():
    """Manual odds entry page."""
    st.title("✍️ Manual Odds Entry")

    st.markdown("""
    Use this page when scrapers fail or for quick odds comparison.
    Enter odds manually and instantly check for +EV and arbitrage.
    """)

    db = DatabaseManager()

    # Tabs for different entry modes
    tab1, tab2, tab3 = st.tabs(["Quick Compare", "Full Event Entry", "Record Bet"])

    with tab1:
        show_quick_compare()

    with tab2:
        show_full_entry(db)

    with tab3:
        show_record_bet(db)


def show_quick_compare():
    """Quick odds comparison calculator."""
    st.subheader("Quick Odds Comparison")

    st.markdown("Enter odds from different bookmakers to check for +EV and arbitrage.")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Event Details**")
        home_team = st.text_input("Home Team", "Team A")
        away_team = st.text_input("Away Team", "Team B")
        is_three_way = st.checkbox("Three-way market (with draw)", value=True)

    with col2:
        st.write("**Sharp Odds (Pinnacle)**")
        pinnacle_home = st.number_input("Pinnacle - Home", 1.01, 50.0, 2.10, 0.01)
        if is_three_way:
            pinnacle_draw = st.number_input("Pinnacle - Draw", 1.01, 50.0, 3.40, 0.01)
        pinnacle_away = st.number_input("Pinnacle - Away", 1.01, 50.0, 3.20, 0.01)

    st.divider()

    # Soft book entries
    st.write("**Soft Bookmaker Odds**")

    col1, col2, col3, col4 = st.columns(4)

    soft_books = {}

    with col1:
        st.write("**Tipsport**")
        soft_books['Tipsport'] = {
            'home': st.number_input("TS Home", 1.01, 50.0, 2.15, 0.01, key='ts_h'),
            'draw': st.number_input("TS Draw", 1.01, 50.0, 3.35, 0.01, key='ts_d') if is_three_way else None,
            'away': st.number_input("TS Away", 1.01, 50.0, 3.15, 0.01, key='ts_a')
        }

    with col2:
        st.write("**Fortuna**")
        soft_books['Fortuna'] = {
            'home': st.number_input("FO Home", 1.01, 50.0, 2.12, 0.01, key='fo_h'),
            'draw': st.number_input("FO Draw", 1.01, 50.0, 3.40, 0.01, key='fo_d') if is_three_way else None,
            'away': st.number_input("FO Away", 1.01, 50.0, 3.25, 0.01, key='fo_a')
        }

    with col3:
        st.write("**Niké**")
        soft_books['Niké'] = {
            'home': st.number_input("NK Home", 1.01, 50.0, 2.18, 0.01, key='nk_h'),
            'draw': st.number_input("NK Draw", 1.01, 50.0, 3.30, 0.01, key='nk_d') if is_three_way else None,
            'away': st.number_input("NK Away", 1.01, 50.0, 3.10, 0.01, key='nk_a')
        }

    with col4:
        st.write("**DOXXbet**")
        soft_books['DOXXbet'] = {
            'home': st.number_input("DX Home", 1.01, 50.0, 2.20, 0.01, key='dx_h'),
            'draw': st.number_input("DX Draw", 1.01, 50.0, 3.45, 0.01, key='dx_d') if is_three_way else None,
            'away': st.number_input("DX Away", 1.01, 50.0, 3.05, 0.01, key='dx_a')
        }

    if st.button("🔍 Analyze", type="primary"):
        # Calculate fair odds from Pinnacle
        if is_three_way:
            sharp_odds = [pinnacle_home, pinnacle_draw, pinnacle_away]
            selections = ['home', 'draw', 'away']
        else:
            sharp_odds = [pinnacle_home, pinnacle_away]
            selections = ['home', 'away']

        fair_odds = OddsConverter.get_true_odds(sharp_odds, 'power')
        fair_probs = {sel: 1/fair for sel, fair in zip(selections, fair_odds)}

        # Display sharp baseline
        st.divider()
        st.subheader("📊 Analysis")

        col1, col2 = st.columns(2)

        with col1:
            st.write("**Sharp Baseline (Pinnacle)**")
            margin = OddsConverter.calculate_margin(sharp_odds)
            st.metric("Margin", f"{margin*100:.2f}%")

            for sel, fair in zip(selections, fair_odds):
                st.write(f"{sel.title()}: {fair:.3f} (fair) | {fair_probs[sel]*100:.1f}%")

        with col2:
            st.write("**Best Odds**")
            for sel in selections:
                best_odds = 0
                best_book = ""
                for book, odds in soft_books.items():
                    if odds[sel] and odds[sel] > best_odds:
                        best_odds = odds[sel]
                        best_book = book

                # Calculate EV
                ev = (fair_probs[sel] * best_odds - 1) * 100

                if ev > 0:
                    st.success(f"{sel.title()}: {best_odds:.2f} ({best_book}) | **+{ev:.1f}% EV**")
                else:
                    st.write(f"{sel.title()}: {best_odds:.2f} ({best_book}) | {ev:.1f}% EV")

        # Check arbitrage
        st.divider()
        st.subheader("💰 Arbitrage Check")

        best_odds_list = []
        for sel in selections:
            best = max(soft_books[book][sel] for book in soft_books if soft_books[book][sel])
            best_odds_list.append(best)

        arb_calc = ArbitrageFinder()
        arb_result = arb_calc.calculate_stakes(best_odds_list, 100)

        if arb_result.get('is_arbitrage'):
            st.success(f"✅ Arbitrage found: **{arb_result['profit_percentage']:.2f}% profit**")
            st.write(f"Stakes: {arb_result['stakes']}")
            st.write(f"Guaranteed profit: €{arb_result['guaranteed_profit']:.2f}")
        else:
            st.info(f"No arbitrage. Combined margin: {arb_result.get('total_implied', 0):.1f}%")


def show_full_entry(db):
    """Full event entry with database storage."""
    st.subheader("Full Event Entry")

    st.markdown("Enter a complete event with odds to save to database.")

    col1, col2 = st.columns(2)

    with col1:
        sport = st.selectbox("Sport", ["Football", "Hockey", "Tennis"])
        league = st.text_input("League", "Slovak Fortuna Liga")
        home_team = st.text_input("Home Team", key="full_home")
        away_team = st.text_input("Away Team", key="full_away")

    with col2:
        start_date = st.date_input("Date", datetime.now().date())
        start_time = st.time_input("Time", datetime.now().time())

    st.write("**Odds (enter for each bookmaker)**")

    # Dynamic bookmaker entry
    num_books = st.number_input("Number of bookmakers", 1, 10, 4)

    bookmaker_odds = {}

    cols = st.columns(min(num_books, 4))
    for i in range(num_books):
        with cols[i % 4]:
            book_name = st.text_input(f"Book {i+1}", f"Book{i+1}", key=f"book_{i}")
            home_odds = st.number_input("Home", 1.01, 50.0, 2.0, key=f"home_{i}")
            draw_odds = st.number_input("Draw", 1.01, 50.0, 3.0, key=f"draw_{i}")
            away_odds = st.number_input("Away", 1.01, 50.0, 3.0, key=f"away_{i}")

            bookmaker_odds[book_name] = {
                'home': home_odds,
                'draw': draw_odds,
                'away': away_odds
            }

    if st.button("💾 Save Event"):
        # Combine date and time
        start_datetime = datetime.combine(start_date, start_time)

        # Save to database
        event_id = db.add_event({
            'sport': sport.lower(),
            'league': league,
            'home_team': home_team,
            'away_team': away_team,
            'start_time': start_datetime
        })

        # Save odds
        for bookmaker, odds in bookmaker_odds.items():
            book = db.get_bookmaker(bookmaker.lower())
            book_id = book.id if book else 1

            for selection, odds_value in odds.items():
                db.add_odds({
                    'event_id': event_id,
                    'bookmaker_id': book_id,
                    'market_type': 'h2h',
                    'selection': selection,
                    'odds_value': odds_value
                })

        st.success(f"Event saved with ID {event_id}!")


def show_record_bet(db):
    """Record a bet directly."""
    st.subheader("Record a Bet")

    col1, col2 = st.columns(2)

    with col1:
        bookmaker = st.selectbox(
            "Bookmaker",
            ["Tipsport", "Fortuna", "Niké", "DOXXbet", "Pinnacle", "Bet365"]
        )
        event_name = st.text_input("Event", "Slovan Bratislava vs Spartak Trnava")
        selection = st.text_input("Selection", "1 (Home)")

    with col2:
        odds = st.number_input("Odds", 1.01, 100.0, 2.00, 0.01)
        stake = st.number_input("Stake (€)", 1.0, 10000.0, 20.0, 1.0)
        sport = st.selectbox("Sport", ["Football", "Hockey", "Tennis"], key="bet_sport")

    # Optional: EV info
    st.write("**Optional: EV Calculation**")
    col1, col2 = st.columns(2)

    with col1:
        true_prob = st.slider("True Probability %", 1, 99, 50) / 100
    with col2:
        sharp_odds = st.number_input("Sharp Odds (Pinnacle)", 1.01, 100.0, odds, 0.01)

    # Calculate EV
    ev = (true_prob * odds - 1) * 100

    if ev > 0:
        st.success(f"**+{ev:.1f}% EV** - Good bet!")
    else:
        st.warning(f"**{ev:.1f}% EV** - Negative expected value")

    if st.button("📝 Record Bet"):
        book = db.get_bookmaker(bookmaker.lower())

        bet_data = {
            'bookmaker_id': book.id if book else 1,
            'sport': sport.lower(),
            'event_name': event_name,
            'selection': selection,
            'odds': odds,
            'stake': stake,
            'potential_return': stake * odds,
            'ev_at_placement': ev,
            'true_probability': true_prob,
            'status': 'pending'
        }

        bet_id = db.add_bet(bet_data)
        st.success(f"Bet recorded with ID {bet_id}!")


if __name__ == "__main__":
    show_manual_entry()
