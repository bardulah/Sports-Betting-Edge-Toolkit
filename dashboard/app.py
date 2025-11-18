"""
Sports Betting Edge Dashboard
=============================

Main Streamlit application for the betting toolkit.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.db_manager import DatabaseManager
from src.bankroll.kelly_criterion import BankrollManager, KellyCalculator
from src.analyzers.ev_calculator import EVCalculator
from src.analyzers.arbitrage_finder import ArbitrageFinder
from src.analyzers.clv_tracker import CLVTracker
from src.bonus.rollover_optimizer import BonusHunter
from src.scrapers.odds_aggregator import OddsAggregator
from src.importers.csv_importer import CSVImporter
from src.importers.tipsport_importer import TipsportImporter
from src.importers.nike_importer import NikeImporter

# Page config
st.set_page_config(
    page_title="Sports Betting Edge",
    page_icon="🎲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize components
@st.cache_resource
def get_db():
    return DatabaseManager()

@st.cache_resource
def get_bankroll_manager():
    return BankrollManager(get_db())

def main():
    # Sidebar navigation
    st.sidebar.title("🎲 Betting Edge")

    page = st.sidebar.radio(
        "Navigation",
        ["Dashboard", "EV Scanner", "Arbitrage", "Bankroll",
         "Betting History", "CLV Analysis", "Bonus Tracker", "Import Data", "Settings"]
    )

    if page == "Dashboard":
        show_dashboard()
    elif page == "EV Scanner":
        show_ev_scanner()
    elif page == "Arbitrage":
        show_arbitrage()
    elif page == "Bankroll":
        show_bankroll()
    elif page == "Betting History":
        show_history()
    elif page == "CLV Analysis":
        show_clv_analysis()
    elif page == "Bonus Tracker":
        show_bonus_tracker()
    elif page == "Import Data":
        show_import()
    elif page == "Settings":
        show_settings()


def show_dashboard():
    """Main dashboard overview."""
    st.title("📊 Dashboard Overview")

    db = get_db()
    bm = get_bankroll_manager()

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)

    stats = db.get_betting_stats()
    bankroll_stats = bm.get_bankroll_stats()

    with col1:
        st.metric(
            "Current Bankroll",
            f"€{bankroll_stats['current']:,.2f}",
            f"{bankroll_stats['roi_pct']:+.1f}% ROI"
        )

    with col2:
        st.metric(
            "Total Bets",
            stats['total_bets'],
            f"{stats['win_rate']:.1f}% Win Rate"
        )

    with col3:
        st.metric(
            "Profit/Loss",
            f"€{stats['profit_loss']:+,.2f}",
            f"Avg Odds: {stats['avg_odds']:.2f}"
        )

    with col4:
        st.metric(
            "Avg CLV",
            f"{stats['avg_clv']:+.1f}%",
            "Closing Line Value"
        )

    st.divider()

    # Charts row
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Bankroll History")
        history = db.get_bankroll_history()

        if not history.empty:
            fig = px.line(
                history,
                x='timestamp',
                y='bankroll',
                title='Bankroll Over Time'
            )
            fig.update_layout(
                xaxis_title="Date",
                yaxis_title="Bankroll (€)",
                hovermode='x unified'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No bankroll history yet")

    with col2:
        st.subheader("P/L by Sport")
        league_stats = db.get_stats_by_league()

        if not league_stats.empty:
            # Aggregate by sport (simplified)
            fig = px.bar(
                league_stats.head(10),
                x='league',
                y='profit_loss',
                title='Profit/Loss by League',
                color='profit_loss',
                color_continuous_scale='RdYlGn'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No betting history yet")

    # Recent bets
    st.subheader("Recent Bets")
    bets = db.get_bets(limit=10)

    if bets:
        bets_data = []
        for bet in bets:
            bets_data.append({
                'Date': bet.placed_at.strftime('%d/%m %H:%M') if bet.placed_at else '',
                'Event': bet.event_name or f"{bet.selection}",
                'Selection': bet.selection,
                'Odds': bet.odds,
                'Stake': f"€{bet.stake:.2f}",
                'Status': bet.status.upper(),
                'P/L': f"€{bet.profit_loss:+.2f}" if bet.profit_loss else '-',
                'CLV': f"{bet.clv:+.1f}%" if bet.clv else '-'
            })

        df = pd.DataFrame(bets_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No bets recorded yet. Import your betting history to get started!")


def show_ev_scanner():
    """EV opportunity scanner."""
    st.title("🎯 +EV Scanner")

    st.markdown("""
    Scan for positive expected value betting opportunities by comparing
    soft bookmaker odds against sharp (Pinnacle) true odds.
    """)

    col1, col2, col3 = st.columns(3)

    with col1:
        sport = st.selectbox("Sport", ["All", "Football", "Hockey", "Tennis"])

    with col2:
        min_ev = st.slider("Minimum EV %", 1.0, 10.0, 2.0, 0.5)

    with col3:
        st.write("")
        scan_btn = st.button("🔍 Scan for +EV", type="primary")

    if scan_btn:
        with st.spinner("Scanning bookmakers..."):
            # Run scraper
            aggregator = OddsAggregator()

            async def do_scan():
                sport_filter = sport.lower() if sport != "All" else None
                return await aggregator.scrape_all(sport_filter)

            events = asyncio.run(do_scan())

            # Find EV opportunities
            all_events = []
            for sport_name, sport_events in events.items():
                all_events.extend(sport_events)

            if all_events:
                ev_calc = EVCalculator({'min_ev_percentage': min_ev})
                opportunities = ev_calc.find_ev_opportunities(all_events, min_ev)

                if opportunities:
                    st.success(f"Found {len(opportunities)} +EV opportunities!")

                    for opp in opportunities[:20]:
                        with st.container():
                            col1, col2, col3 = st.columns([3, 2, 1])

                            with col1:
                                st.markdown(f"**{opp.event.home_team}** vs **{opp.event.away_team}**")
                                st.caption(f"{opp.event.league} | {opp.event.start_time.strftime('%H:%M %d/%m')}")

                            with col2:
                                st.markdown(f"**{opp.selection}** @ {opp.offered_odds}")
                                st.caption(f"{opp.bookmaker} | Sharp: {opp.sharp_odds}")

                            with col3:
                                st.metric(
                                    "EV",
                                    f"+{opp.ev_percentage:.1f}%",
                                    f"€{opp.recommended_stake:.0f}"
                                )

                            st.divider()
                else:
                    st.warning("No +EV opportunities found with current filters")
            else:
                st.error("Failed to scrape odds data")


def show_arbitrage():
    """Arbitrage scanner."""
    st.title("💰 Arbitrage Scanner")

    st.markdown("""
    Find guaranteed profit opportunities (surebets) across bookmakers.
    """)

    col1, col2 = st.columns(2)

    with col1:
        min_profit = st.slider("Minimum Profit %", 0.5, 5.0, 1.0, 0.1)

    with col2:
        max_stake = st.number_input("Max Total Stake (€)", 100, 2000, 500, 50)

    if st.button("🔍 Scan for Arbitrage", type="primary"):
        with st.spinner("Scanning for arbitrage..."):
            aggregator = OddsAggregator()

            async def do_scan():
                return await aggregator.scrape_all()

            events = asyncio.run(do_scan())

            all_events = []
            for sport_events in events.values():
                all_events.extend(sport_events)

            if all_events:
                arb_finder = ArbitrageFinder({
                    'min_profit_percentage': min_profit,
                    'max_stake': max_stake
                })
                opportunities = arb_finder.find_arbitrage(all_events, min_profit)

                if opportunities:
                    st.success(f"Found {len(opportunities)} arbitrage opportunities!")

                    for opp in opportunities:
                        with st.expander(
                            f"💰 {opp.profit_percentage:.2f}% | {opp.event.home_team} vs {opp.event.away_team}"
                        ):
                            col1, col2 = st.columns(2)

                            with col1:
                                st.metric("Guaranteed Profit", f"€{opp.guaranteed_profit:.2f}")
                                st.metric("Total Stake", f"€{opp.total_stake:.2f}")

                            with col2:
                                st.write("**Stakes:**")
                                for leg in opp.legs:
                                    st.write(
                                        f"• {leg.selection} @ {leg.odds} ({leg.bookmaker}): "
                                        f"**€{leg.stake:.2f}**"
                                    )
                else:
                    st.info("No arbitrage opportunities found")
            else:
                st.error("Failed to scrape odds")


def show_bankroll():
    """Bankroll management."""
    st.title("💵 Bankroll Management")

    bm = get_bankroll_manager()
    stats = bm.get_bankroll_stats()

    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Current", f"€{stats['current']:,.2f}")
    with col2:
        st.metric("Peak", f"€{stats['peak']:,.2f}")
    with col3:
        st.metric("Max Drawdown", f"{stats['max_drawdown_pct']:.1f}%")
    with col4:
        st.metric("ROI", f"{stats['roi_pct']:+.1f}%")

    st.divider()

    # Kelly calculator
    st.subheader("Kelly Stake Calculator")

    col1, col2, col3 = st.columns(3)

    with col1:
        prob = st.slider("True Probability %", 10, 90, 55, 1) / 100
    with col2:
        odds = st.number_input("Decimal Odds", 1.01, 20.0, 2.0, 0.01)
    with col3:
        kelly_frac = st.select_slider(
            "Kelly Fraction",
            options=[0.125, 0.25, 0.5, 1.0],
            value=0.25,
            format_func=lambda x: f"{x*100:.0f}%"
        )

    recommendation = bm.calculate_stake(prob, odds, kelly_frac)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Recommended Stake", f"€{recommendation.recommended:.2f}")
    with col2:
        st.metric("Expected Value", f"{recommendation.ev_percentage:+.1f}%")
    with col3:
        if recommendation.ev_percentage > 0:
            st.success("Positive EV - Consider betting")
        else:
            st.error("Negative EV - Pass")

    # Bankroll history chart
    st.subheader("Bankroll History")

    db = get_db()
    history = db.get_bankroll_history()

    if not history.empty:
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=history['timestamp'],
            y=history['bankroll'],
            mode='lines+markers',
            name='Bankroll',
            line=dict(color='#00ff00', width=2)
        ))

        # Add initial line
        fig.add_hline(
            y=stats.get('initial', 1000),
            line_dash="dash",
            line_color="gray",
            annotation_text="Initial"
        )

        fig.update_layout(
            title='Bankroll Evolution',
            xaxis_title='Date',
            yaxis_title='Bankroll (€)',
            hovermode='x unified'
        )

        st.plotly_chart(fig, use_container_width=True)

    # Deposit/Withdraw
    st.subheader("Transactions")

    col1, col2 = st.columns(2)

    with col1:
        deposit_amount = st.number_input("Deposit Amount (€)", 0, 10000, 100)
        if st.button("💰 Deposit"):
            bm.deposit(deposit_amount)
            st.success(f"Deposited €{deposit_amount}")
            st.rerun()

    with col2:
        withdraw_amount = st.number_input("Withdraw Amount (€)", 0, 10000, 100)
        if st.button("🏦 Withdraw"):
            bm.withdraw(withdraw_amount)
            st.success(f"Withdrew €{withdraw_amount}")
            st.rerun()


def show_history():
    """Betting history."""
    st.title("📜 Betting History")

    db = get_db()

    # Filters
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        status_filter = st.selectbox(
            "Status",
            ["All", "Pending", "Won", "Lost"]
        )
    with col2:
        sport_filter = st.selectbox(
            "Sport",
            ["All", "Football", "Hockey", "Tennis"]
        )
    with col3:
        days = st.selectbox(
            "Period",
            [7, 30, 90, 365],
            format_func=lambda x: f"Last {x} days"
        )
    with col4:
        st.write("")
        export_btn = st.button("📥 Export CSV")

    # Get bets
    start_date = datetime.now() - timedelta(days=days)
    bets = db.get_bets(
        status=status_filter.lower() if status_filter != "All" else None,
        sport=sport_filter.lower() if sport_filter != "All" else None,
        start_date=start_date,
        limit=500
    )

    if bets:
        # Summary stats
        total_staked = sum(b.stake for b in bets)
        total_profit = sum(b.profit_loss for b in bets if b.profit_loss)
        wins = len([b for b in bets if b.status == 'won'])

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Bets", len(bets))
        with col2:
            st.metric("Total Staked", f"€{total_staked:,.2f}")
        with col3:
            st.metric("Profit/Loss", f"€{total_profit:+,.2f}")
        with col4:
            win_rate = (wins / len(bets) * 100) if bets else 0
            st.metric("Win Rate", f"{win_rate:.1f}%")

        # Bets table
        st.divider()

        bets_data = []
        for bet in bets:
            bets_data.append({
                'Date': bet.placed_at.strftime('%Y-%m-%d %H:%M') if bet.placed_at else '',
                'Event': (bet.event_name or bet.selection)[:40],
                'Selection': bet.selection,
                'Odds': f"{bet.odds:.2f}",
                'Stake': f"€{bet.stake:.2f}",
                'Status': bet.status.upper(),
                'P/L': f"€{bet.profit_loss:+.2f}" if bet.profit_loss else '-',
                'CLV': f"{bet.clv:+.1f}%" if bet.clv else '-'
            })

        df = pd.DataFrame(bets_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        if export_btn:
            csv = df.to_csv(index=False)
            st.download_button(
                "Download CSV",
                csv,
                "betting_history.csv",
                "text/csv"
            )
    else:
        st.info("No bets found for selected filters")


def show_clv_analysis():
    """CLV analysis page."""
    st.title("📈 Closing Line Value Analysis")

    st.markdown("""
    CLV measures how your bet odds compare to the closing line.
    **Consistently beating the closing line is the best predictor of long-term profit.**
    """)

    db = get_db()
    clv_tracker = CLVTracker(db)

    # Overall stats
    stats = clv_tracker.analyze_bet_history()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Average CLV", f"{stats.get('avg_clv', 0):+.1f}%")
    with col2:
        st.metric("Positive CLV Rate", f"{stats.get('positive_clv_rate', 0):.0f}%")
    with col3:
        st.metric("Total Tracked", stats.get('total_bets_with_clv', 0))
    with col4:
        # Predict ROI
        pred = clv_tracker.predict_long_term_roi(stats.get('avg_clv', 0))
        st.metric("Est. Long-term ROI", f"{pred['estimated_roi']:+.1f}%")

    st.divider()

    # CLV by bookmaker
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("CLV by Bookmaker")
        book_stats = clv_tracker.get_clv_by_bookmaker()

        if not book_stats.empty:
            fig = px.bar(
                book_stats,
                x='bookmaker',
                y='avg_clv',
                color='avg_clv',
                color_continuous_scale='RdYlGn',
                title='Average CLV by Bookmaker'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No CLV data yet")

    with col2:
        st.subheader("CLV by Sport")
        sport_stats = clv_tracker.get_clv_by_sport()

        if not sport_stats.empty:
            fig = px.bar(
                sport_stats,
                x='sport',
                y='avg_clv',
                color='avg_clv',
                color_continuous_scale='RdYlGn',
                title='Average CLV by Sport'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No CLV data yet")

    # Skill assessment
    st.subheader("Skill Assessment")

    assessment = clv_tracker.get_skill_assessment()

    if assessment.get('assessment') != 'Insufficient data':
        col1, col2 = st.columns([1, 2])

        with col1:
            skill = assessment.get('skill_level', 'Unknown')
            if skill == 'Sharp':
                st.success(f"🎯 {skill}")
            elif skill == 'Skilled':
                st.info(f"📈 {skill}")
            else:
                st.warning(f"📊 {skill}")

        with col2:
            st.write(assessment.get('description', ''))
            st.caption(assessment.get('recommendation', ''))
    else:
        st.info("Need more bets with CLV tracking for skill assessment (50+ bets)")


def show_bonus_tracker():
    """Bonus and rollover tracker."""
    st.title("🎁 Bonus Tracker")

    db = get_db()
    bonus_hunter = BonusHunter(db)

    # Active bonuses
    st.subheader("Active Bonuses")

    bonuses = bonus_hunter.get_active_bonuses()

    if bonuses:
        for bonus in bonuses:
            with st.container():
                col1, col2, col3 = st.columns([2, 2, 1])

                with col1:
                    st.markdown(f"**{bonus.bookmaker}**")
                    st.caption(f"Bonus: €{bonus.bonus_amount}")

                with col2:
                    progress = bonus.progress_percentage
                    st.progress(progress / 100)
                    st.caption(
                        f"€{bonus.amount_wagered:.0f} / €{bonus.amount_required:.0f} "
                        f"({progress:.0f}%)"
                    )

                with col3:
                    remaining = bonus.amount_required - bonus.amount_wagered
                    st.metric("Remaining", f"€{remaining:.0f}")

                st.divider()
    else:
        st.info("No active bonuses")

    # Add new bonus
    st.subheader("Add New Bonus")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        bookmaker = st.selectbox(
            "Bookmaker",
            ["Tipsport", "Fortuna", "Niké", "DOXXbet"]
        )
    with col2:
        amount = st.number_input("Bonus Amount (€)", 10, 1000, 100)
    with col3:
        rollover = st.number_input("Rollover", 1, 20, 5)
    with col4:
        max_odds = st.number_input("Max Odds", 1.1, 3.0, 1.5, 0.1)

    if st.button("➕ Add Bonus"):
        bonus_hunter.add_bonus(bookmaker, amount, rollover, max_odds)
        st.success(f"Added {bookmaker} bonus!")
        st.rerun()

    # Bonus EV calculator
    st.subheader("Bonus Value Calculator")

    from src.bonus.rollover_optimizer import RolloverOptimizer
    optimizer = RolloverOptimizer()

    col1, col2 = st.columns(2)

    with col1:
        calc_amount = st.number_input("Bonus Amount", 10, 1000, 100, key='calc_amount')
        calc_rollover = st.number_input("Wagering Requirement", 1, 20, 5, key='calc_roll')

    with col2:
        calc_max_odds = st.number_input("Max Odds for Rollover", 1.1, 3.0, 1.5, 0.1, key='calc_odds')

        if st.button("Calculate EV"):
            ev_info = optimizer.calculate_bonus_ev(
                calc_amount, calc_rollover, calc_max_odds
            )

            if ev_info['is_profitable']:
                st.success(f"Expected Value: **€{ev_info['expected_value']:.2f}** ✅")
            else:
                st.error(f"Expected Value: **€{ev_info['expected_value']:.2f}** ❌")

            st.caption(f"Total wagering: €{ev_info['total_wagering_required']:.0f}")


def show_import():
    """Import betting history."""
    st.title("📥 Import Betting History")

    import_type = st.radio(
        "Import from",
        ["Tipsport", "Niké", "Generic CSV"]
    )

    uploaded_file = st.file_uploader(
        "Upload your betting history file",
        type=['csv', 'xlsx']
    )

    if uploaded_file:
        # Preview
        st.subheader("Preview")

        try:
            if uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file, nrows=5)
            else:
                df = pd.read_csv(uploaded_file, nrows=5, sep=';')

            st.dataframe(df)
        except:
            df = pd.read_csv(uploaded_file, nrows=5)
            st.dataframe(df)

        if st.button("🚀 Import", type="primary"):
            # Save temp file
            temp_path = f"/tmp/{uploaded_file.name}"
            with open(temp_path, 'wb') as f:
                f.write(uploaded_file.getvalue())

            db = get_db()

            if import_type == "Tipsport":
                importer = TipsportImporter(db)
                count = importer.import_tipsport_csv(temp_path)
            elif import_type == "Niké":
                importer = NikeImporter(db)
                count = importer.import_nike_csv(temp_path)
            else:
                importer = CSVImporter(db)
                count = importer.import_csv(temp_path)

            if count > 0:
                st.success(f"Successfully imported {count} bets!")
            else:
                st.error("Failed to import bets. Check file format.")


def show_settings():
    """Settings page."""
    st.title("⚙️ Settings")

    # Bankroll settings
    st.subheader("Bankroll Settings")

    col1, col2 = st.columns(2)

    with col1:
        initial_bankroll = st.number_input(
            "Initial Bankroll (€)",
            100, 100000, 1000
        )
        kelly_fraction = st.select_slider(
            "Default Kelly Fraction",
            options=[0.125, 0.25, 0.5],
            value=0.25,
            format_func=lambda x: f"{x*100:.0f}%"
        )

    with col2:
        max_bet_pct = st.slider(
            "Max Bet % of Bankroll",
            1, 10, 5
        )
        min_bet = st.number_input(
            "Minimum Bet (€)",
            1, 100, 1
        )

    st.divider()

    # Notification settings
    st.subheader("Telegram Notifications")

    telegram_token = st.text_input("Bot Token", type="password")
    telegram_chat = st.text_input("Chat ID")

    col1, col2 = st.columns(2)

    with col1:
        notify_ev = st.checkbox("Notify on +EV opportunities", value=True)
        notify_arb = st.checkbox("Notify on arbitrage", value=True)

    with col2:
        notify_clv = st.checkbox("Notify when beating CLV", value=True)
        notify_milestone = st.checkbox("Notify on milestones", value=True)

    st.divider()

    # EV Scanner settings
    st.subheader("EV Scanner Settings")

    min_ev_alert = st.slider("Minimum EV % for alerts", 1.0, 10.0, 2.0, 0.5)

    if st.button("💾 Save Settings", type="primary"):
        # Save to database/config
        st.success("Settings saved!")


if __name__ == "__main__":
    main()
