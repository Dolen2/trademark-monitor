"""
Streamlit Dashboard for Trademark Monitoring System.
Provides a web interface for viewing conflicts, managing trademarks, and monitoring status.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import TrademarkDatabase
from src.monitor import TrademarkMonitor
from src.data_fetcher import USPTODataFetcher

# Page configuration
st.set_page_config(
    page_title="Trademark Monitor - Relatent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f4e79;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        color: #666;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
    }
    .conflict-high {
        background-color: #ffebee;
        border-left: 4px solid #dc3545;
        padding: 15px;
        margin: 10px 0;
        border-radius: 4px;
    }
    .conflict-medium {
        background-color: #fff3e0;
        border-left: 4px solid #ff9800;
        padding: 15px;
        margin: 10px 0;
        border-radius: 4px;
    }
    .conflict-low {
        background-color: #e8f5e9;
        border-left: 4px solid #4caf50;
        padding: 15px;
        margin: 10px 0;
        border-radius: 4px;
    }
    .status-new { color: #dc3545; font-weight: bold; }
    .status-reviewed { color: #ff9800; }
    .status-dismissed { color: #6c757d; }
    .status-action_taken { color: #28a745; }
</style>
""", unsafe_allow_html=True)


# Initialize session state
if 'db' not in st.session_state:
    st.session_state.db = TrademarkDatabase('data/trademark_monitor.db')

if 'monitor' not in st.session_state:
    try:
        st.session_state.monitor = TrademarkMonitor(config_path='config/config.yaml')
    except Exception as e:
        st.session_state.monitor = None
        st.session_state.monitor_error = str(e)


def get_db():
    return st.session_state.db


def get_monitor():
    return st.session_state.monitor


# Sidebar navigation
st.sidebar.markdown("## 🔍 Trademark Monitor")
st.sidebar.markdown("*Relatent, Inc.*")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["📊 Dashboard", "⚠️ Conflicts", "📋 Our Trademarks", "🔄 Run Monitor", "⚙️ Settings"],
    index=0
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Quick Stats")
stats = get_db().get_dashboard_stats()
st.sidebar.metric("Total Processed", f"{stats['total_processed']:,}")
st.sidebar.metric("Active Conflicts", stats['conflict_stats'].get('new', 0))


# ==================== Dashboard Page ====================
if page == "📊 Dashboard":
    st.markdown('<p class="main-header">📊 Trademark Monitoring Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Monitor potential trademark conflicts for TOPO and TOPOLOGY</p>', unsafe_allow_html=True)

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="🔍 Filings Processed",
            value=f"{stats['total_processed']:,}",
            delta=None
        )

    with col2:
        new_conflicts = stats['conflict_stats'].get('new', 0)
        st.metric(
            label="⚠️ New Conflicts",
            value=new_conflicts,
            delta=f"+{new_conflicts}" if new_conflicts > 0 else None,
            delta_color="inverse"
        )

    with col3:
        total_conflicts = stats['conflict_stats'].get('total', 0)
        st.metric(
            label="📋 Total Conflicts",
            value=total_conflicts
        )

    with col4:
        last_run = stats.get('last_run')
        if last_run:
            last_run_time = datetime.fromisoformat(last_run['start_time'])
            time_ago = datetime.now() - last_run_time
            if time_ago.days > 0:
                time_str = f"{time_ago.days}d ago"
            elif time_ago.seconds > 3600:
                time_str = f"{time_ago.seconds // 3600}h ago"
            else:
                time_str = f"{time_ago.seconds // 60}m ago"
        else:
            time_str = "Never"
        st.metric(label="🕐 Last Run", value=time_str)

    st.markdown("---")

    # Recent conflicts
    st.subheader("⚠️ Recent Potential Conflicts")

    conflicts = get_db().get_flagged_conflicts(limit=10)

    if not conflicts:
        st.info("No conflicts detected yet. Run the monitor to scan for potential conflicts.")
    else:
        for conflict in conflicts:
            score = conflict['similarity_score']
            if score >= 85:
                severity_class = "conflict-high"
                severity_emoji = "🔴"
            elif score >= 75:
                severity_class = "conflict-medium"
                severity_emoji = "🟠"
            else:
                severity_class = "conflict-low"
                severity_emoji = "🟡"

            with st.container():
                st.markdown(f'<div class="{severity_class}">', unsafe_allow_html=True)

                col1, col2, col3 = st.columns([3, 2, 1])

                with col1:
                    st.markdown(f"### {severity_emoji} {conflict['mark_text']}")
                    st.markdown(f"**Serial:** {conflict['serial_number']} | **Matched:** `{conflict['matched_trademark']}`")
                    st.markdown(f"**Classes:** {conflict['classes']} | **Applicant:** {conflict['applicant_name']}")

                with col2:
                    st.markdown(f"**Similarity Score**")
                    st.progress(score / 100)
                    st.markdown(f"**{score:.1f}%**")

                with col3:
                    status = conflict['status']
                    st.markdown(f"<span class='status-{status}'>{status.upper()}</span>", unsafe_allow_html=True)
                    st.markdown(f"[View on TSDR ↗](https://tsdr.uspto.gov/#caseNumber={conflict['serial_number']}&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch)")

                st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")

    # Our trademarks status
    st.subheader("📋 Our Trademark Applications")

    our_tms = stats.get('our_trademarks', [])
    if our_tms:
        tm_df = pd.DataFrame(our_tms)
        tm_df['TSDR Link'] = tm_df['serial_number'].apply(
            lambda x: f"https://tsdr.uspto.gov/#caseNumber={x}&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch"
        )

        for tm in our_tms:
            col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
            with col1:
                st.markdown(f"**{tm['name']}**")
            with col2:
                st.markdown(f"Serial: {tm['serial_number']}")
            with col3:
                classes = tm.get('classes', [])
                if isinstance(classes, str):
                    import json
                    try:
                        classes = json.loads(classes)
                    except:
                        pass
                st.markdown(f"Classes: {classes}")
            with col4:
                st.markdown(f"[View TSDR ↗](https://tsdr.uspto.gov/#caseNumber={tm['serial_number']}&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch)")


# ==================== Conflicts Page ====================
elif page == "⚠️ Conflicts":
    st.markdown("# ⚠️ Potential Conflicts")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox(
            "Filter by Status",
            ["All", "new", "reviewed", "dismissed", "action_taken"]
        )
    with col2:
        matched_filter = st.selectbox(
            "Filter by Matched Mark",
            ["All", "TOPO", "TOPOLOGY"]
        )
    with col3:
        sort_by = st.selectbox(
            "Sort by",
            ["Newest First", "Score (High to Low)", "Score (Low to High)"]
        )

    # Get conflicts
    if status_filter == "All":
        conflicts = get_db().get_flagged_conflicts(limit=100)
    else:
        conflicts = get_db().get_flagged_conflicts(status=status_filter, limit=100)

    # Apply filters
    if matched_filter != "All":
        conflicts = [c for c in conflicts if c['matched_trademark'] == matched_filter]

    # Sort
    if sort_by == "Score (High to Low)":
        conflicts = sorted(conflicts, key=lambda x: x['similarity_score'], reverse=True)
    elif sort_by == "Score (Low to High)":
        conflicts = sorted(conflicts, key=lambda x: x['similarity_score'])

    st.markdown(f"**{len(conflicts)} conflicts found**")
    st.markdown("---")

    if not conflicts:
        st.info("No conflicts match the current filters.")
    else:
        for i, conflict in enumerate(conflicts):
            with st.expander(
                f"{conflict['mark_text']} - Score: {conflict['similarity_score']:.1f}% - {conflict['status'].upper()}",
                expanded=i < 3
            ):
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.markdown(f"### {conflict['mark_text']}")
                    st.markdown(f"**Serial Number:** {conflict['serial_number']}")
                    st.markdown(f"**Matched Against:** `{conflict['matched_trademark']}`")
                    st.markdown(f"**Filing Date:** {conflict['filing_date']}")
                    st.markdown(f"**Classes:** {conflict['classes']}")
                    st.markdown(f"**Applicant:** {conflict['applicant_name']}")
                    st.markdown(f"**Goods/Services:** {conflict['goods_services'][:300] if conflict['goods_services'] else 'N/A'}...")

                    # Similarity reasons
                    if conflict.get('similarity_reasons'):
                        st.markdown("**Why Flagged:**")
                        reasons = conflict['similarity_reasons']
                        if isinstance(reasons, dict):
                            for category, details in reasons.items():
                                if isinstance(details, dict):
                                    for k, v in details.items():
                                        st.markdown(f"- {v}")
                                elif isinstance(details, list):
                                    for item in details:
                                        st.markdown(f"- {item}")

                with col2:
                    st.markdown("### Actions")

                    tsdr_link = f"https://tsdr.uspto.gov/#caseNumber={conflict['serial_number']}&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch"
                    st.markdown(f"[🔗 View on USPTO TSDR]({tsdr_link})")

                    st.markdown("---")

                    # Status update buttons
                    st.markdown("**Update Status:**")

                    if conflict['status'] != 'reviewed':
                        if st.button(f"✅ Mark Reviewed", key=f"review_{conflict['id']}"):
                            get_db().update_conflict_status(conflict['id'], 'reviewed')
                            st.rerun()

                    if conflict['status'] != 'dismissed':
                        if st.button(f"❌ Dismiss", key=f"dismiss_{conflict['id']}"):
                            get_db().update_conflict_status(conflict['id'], 'dismissed')
                            st.rerun()

                    if conflict['status'] != 'action_taken':
                        if st.button(f"⚡ Action Taken", key=f"action_{conflict['id']}"):
                            get_db().update_conflict_status(conflict['id'], 'action_taken')
                            st.rerun()

                    # Notes
                    notes = st.text_area(f"Notes", value=conflict.get('notes', ''), key=f"notes_{conflict['id']}")
                    if st.button("Save Notes", key=f"save_notes_{conflict['id']}"):
                        get_db().update_conflict_status(conflict['id'], conflict['status'], notes)
                        st.success("Notes saved!")


# ==================== Our Trademarks Page ====================
elif page == "📋 Our Trademarks":
    st.markdown("# 📋 Our Trademark Applications")
    st.markdown("Monitor the status of Relatent's trademark filings.")

    our_marks = get_db().get_our_trademarks()

    if not our_marks:
        st.warning("No trademarks registered in the system.")
    else:
        for tm in our_marks:
            st.markdown("---")
            col1, col2, col3 = st.columns([2, 2, 2])

            with col1:
                st.markdown(f"## {tm['name']}")
                st.markdown(f"**Serial Number:** {tm['serial_number']}")

            with col2:
                classes = tm.get('classes', [])
                if isinstance(classes, str):
                    import json
                    try:
                        classes = json.loads(classes)
                    except:
                        pass
                st.markdown(f"**Classes:** {classes}")
                st.markdown(f"**Status:** {tm.get('status', 'Unknown')}")

            with col3:
                tsdr_link = f"https://tsdr.uspto.gov/#caseNumber={tm['serial_number']}&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch"
                st.markdown(f"[🔗 View on USPTO TSDR]({tsdr_link})")

                if tm.get('last_checked'):
                    st.markdown(f"*Last checked: {tm['last_checked'][:10]}*")

    st.markdown("---")

    # Check status button
    if st.button("🔄 Check Current Status on USPTO"):
        with st.spinner("Checking status with USPTO TSDR API..."):
            monitor = get_monitor()
            if monitor:
                try:
                    results = monitor.check_our_marks_status()
                    st.success("Status check complete!")
                    for r in results:
                        st.markdown(f"- **{r['name']}** ({r['serial_number']}): {r['status']}")
                except Exception as e:
                    st.error(f"Error checking status: {e}")
            else:
                st.error("Monitor not initialized. Check configuration.")


# ==================== Run Monitor Page ====================
elif page == "🔄 Run Monitor":
    st.markdown("# 🔄 Run Monitoring Scan")
    st.markdown("Scan USPTO data for potential trademark conflicts.")

    st.warning("""
    **Note:** Running the monitor will:
    1. Download recent USPTO trademark filing data
    2. Parse and analyze new filings
    3. Flag potential conflicts with TOPO and TOPOLOGY
    4. Send alerts if configured
    """)

    col1, col2 = st.columns(2)

    with col1:
        days_back = st.slider("Days to scan", 1, 30, 7)

    with col2:
        use_sample = st.checkbox("Use sample data (for testing)", value=False)

    if st.button("🚀 Run Monitor Now", type="primary"):
        monitor = get_monitor()

        if not monitor:
            st.error("Monitor not initialized. Check configuration.")
        else:
            with st.spinner("Running trademark scan... This may take a few minutes."):
                try:
                    results = monitor.run(days_back=days_back, use_sample_data=use_sample)

                    st.success("Monitoring scan complete!")

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Files Processed", results['files_processed'])
                    with col2:
                        st.metric("Filings Analyzed", results['filings_processed'])
                    with col3:
                        st.metric("Conflicts Found", results['conflicts_found'])

                    if results['conflicts_found'] > 0:
                        st.warning(f"⚠️ Found {results['conflicts_found']} potential conflicts! Check the Conflicts page.")

                except Exception as e:
                    st.error(f"Error running monitor: {e}")
                    import traceback
                    st.code(traceback.format_exc())

    st.markdown("---")

    # Recent runs
    st.subheader("📜 Recent Monitoring Runs")

    recent_runs = get_db().get_recent_runs(limit=10)

    if recent_runs:
        runs_df = pd.DataFrame(recent_runs)
        runs_df['start_time'] = pd.to_datetime(runs_df['start_time'])
        runs_df = runs_df[['start_time', 'status', 'files_processed', 'filings_processed', 'conflicts_found']]
        runs_df.columns = ['Time', 'Status', 'Files', 'Filings', 'Conflicts']
        st.dataframe(runs_df, use_container_width=True)
    else:
        st.info("No monitoring runs yet.")


# ==================== Settings Page ====================
elif page == "⚙️ Settings":
    st.markdown("# ⚙️ Settings")

    st.subheader("Alert Configuration")
    st.markdown("""
    Configure your alert settings in the `config/config.yaml` file or via environment variables:

    **Email Alerts:**
    - `SMTP_SERVER` - SMTP server address
    - `SMTP_USERNAME` - SMTP username
    - `SMTP_PASSWORD` - SMTP password
    - `ALERT_FROM_EMAIL` - Sender email address
    - `ALERT_TO_EMAIL` - Recipient email address

    **Slack Alerts:**
    - `SLACK_WEBHOOK_URL` - Slack webhook URL
    """)

    st.subheader("USPTO API Key")
    st.markdown("""
    For detailed trademark lookups, you can register for a free USPTO API key:
    1. Visit [developer.uspto.gov](https://developer.uspto.gov)
    2. Create an account
    3. Register for TSDR API access
    4. Set the `USPTO_API_KEY` environment variable
    """)

    st.subheader("Test Alerts")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📧 Test Email Alert"):
            monitor = get_monitor()
            if monitor:
                try:
                    result = monitor.alerts.test_email()
                    if result:
                        st.success("Test email sent successfully!")
                    else:
                        st.error("Failed to send test email. Check configuration.")
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.error("Monitor not initialized.")

    with col2:
        if st.button("💬 Test Slack Alert"):
            monitor = get_monitor()
            if monitor:
                try:
                    result = monitor.alerts.test_slack()
                    if result:
                        st.success("Test Slack message sent!")
                    else:
                        st.error("Failed to send Slack message. Check webhook URL.")
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.error("Monitor not initialized.")

    st.markdown("---")

    st.subheader("Database")
    st.markdown(f"**Database Location:** `data/trademark_monitor.db`")

    db_stats = get_db().get_dashboard_stats()
    st.markdown(f"- Total processed filings: {db_stats['total_processed']:,}")
    st.markdown(f"- Total conflicts: {db_stats['conflict_stats'].get('total', 0)}")

    if st.button("🗑️ Clear All Data", type="secondary"):
        st.warning("This will delete all monitoring data. Are you sure?")
        if st.button("Yes, delete everything"):
            import os
            os.remove('data/trademark_monitor.db')
            st.session_state.db = TrademarkDatabase('data/trademark_monitor.db')
            st.success("Database cleared!")
            st.rerun()


# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("""
<small>
Trademark Monitor v1.0<br>
© 2026 Relatent, Inc.<br>
</small>
""", unsafe_allow_html=True)
