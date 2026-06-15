#!/usr/bin/env python3
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml


def load_config():
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


@st.cache_data(ttl=60)
def load_data(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM job_proposals ORDER BY created_at DESC", conn)
    conn.close()

    if df.empty:
        return df

    df["_parsed_date"] = pd.to_datetime(df["email_received_date"], errors="coerce", utc=True)
    df["_created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    fallback = df["_created_at"].fillna(pd.Timestamp.now())
    df["_parsed_date"] = df["_parsed_date"].fillna(fallback)

    def best_level(row):
        levels = {"High": 3, "Medium": 2, "Low": 1, None: 0, "Error": 0}
        r = levels.get(row.get("resume_match_level"), 0)
        e = levels.get(row.get("expectations_match_level"), 0)
        return min(r, e)

    level_map = {3: "High", 2: "Medium", 1: "Low", 0: None}
    df["_best_level"] = df.apply(best_level, axis=1)
    df["_best_label"] = df["_best_level"].map(level_map)
    df["_best_label"] = df["_best_label"].fillna("N/A")
    return df


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    date_filter = st.sidebar.selectbox(
        "Date range",
        ["All time", "Last 7 days", "Last 30 days", "Last 90 days", "Custom"],
    )

    if date_filter == "Custom":
        col1, col2 = st.sidebar.columns(2)
        start = col1.date_input("From", datetime.today() - timedelta(days=7))
        end = col2.date_input("To", datetime.today())
        cutoff_start = pd.Timestamp(start)
        cutoff_end = pd.Timestamp(end) + timedelta(days=1)
        df = df[(df["_parsed_date"] >= cutoff_start) & (df["_parsed_date"] <= cutoff_end)]
    elif date_filter != "All time":
        days = int(date_filter.split()[1])
        cutoff = pd.Timestamp.now() - timedelta(days=days)
        df = df[df["_parsed_date"] >= cutoff]

    match_filter = st.sidebar.selectbox(
        "Match filter",
        ["All matches", "High only", "Medium or higher", "Low only"],
    )
    if match_filter == "High only":
        df = df[df["_best_level"] >= 3]
    elif match_filter == "Medium or higher":
        df = df[df["_best_level"] >= 2]
    elif match_filter == "Low only":
        df = df[(df["_best_level"] <= 1) | (df["_best_level"].isna())]

    return df


def render_stats(df: pd.DataFrame):
    total = len(df)
    high = len(df[df["_best_label"] == "High"])
    medium = len(df[df["_best_label"] == "Medium"])
    low = len(df[(df["_best_label"] == "Low") | (df["_best_label"] == "N/A")])

    cols = st.columns(4)
    cols[0].metric("Total Proposals", total)
    cols[1].metric("High Match", high, border=True)
    cols[2].metric("Medium Match", medium, border=True)
    cols[3].metric("Low Match", low, border=True)


def render_table(df: pd.DataFrame):
    if df.empty:
        st.info("No proposals match the selected filters.")
        return None

    icon_map = {"High": "🟢", "Medium": "🟠", "Low": "🔴"}

    cols = {
        "job_title": "Job Title",
        "company": "Company",
        "location": "Location",
        "salary": "Salary",
        "_best_label": "Best Match",
        "resume_match_level": "Resume",
        "expectations_match_level": "Expect.",
        "_parsed_date": "Date",
    }
    display = df[list(cols.keys())].copy()
    display["_best_label"] = display["_best_label"].map(icon_map).fillna("⚪")
    display["_parsed_date"] = (
        pd.to_datetime(display["_parsed_date"], errors="coerce")
        .dt.strftime("%Y-%m-%d")
        .fillna("")
    )

    selection = st.dataframe(
        display,
        column_config={k: v for k, v in cols.items()},
        on_select="rerun",
        selection_mode="single-row",
        width="stretch",
        hide_index=True,
    )

    if selection.selection.rows:
        return df.iloc[selection.selection.rows[0]]
    return None


def render_detail(row: pd.Series):
    if row is None:
        return

    emoji_map = {"High": "🟢", "Medium": "🟠", "Low": "🔴"}
    r_emoji = emoji_map.get(row["resume_match_level"], "⚪")
    e_emoji = emoji_map.get(row["expectations_match_level"], "⚪")

    st.subheader(f"{row['job_title']} @ {row['company']}")
    st.write(f"**Email:** {row['email_subject']}")
    st.write(f"**From:** {row['email_from']}")
    st.write(f"**Date:** {row['_parsed_date'].strftime('%Y-%m-%d %H:%M')}")
    st.write(f"**URL:** [{row['job_url']}]({row['job_url']})")
    st.write(f"**Salary:** {row.get('salary') or 'N/A'}  |  **Location:** {row.get('location') or 'N/A'}")

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Resume Match:** {r_emoji} {row['resume_match_level'] or 'N/A'}")
        st.caption(row.get("resume_match_summary") or "No summary available")
    with col2:
        st.markdown(f"**Expectations Match:** {e_emoji} {row['expectations_match_level'] or 'N/A'}")
        st.caption(row.get("expectations_match_summary") or "No summary available")

    if row.get("error"):
        st.warning(f"Error: {row['error']}")


def parse_interval(label: str) -> int:
    return {"15s": 15, "30s": 30, "1min": 60, "5min": 300}[label]


def render_refresh():
    st.sidebar.divider()
    st.sidebar.header("Refresh")

    auto_refresh = st.sidebar.toggle("Auto-refresh", value=False)
    interval_label = st.sidebar.selectbox("Interval", ["15s", "30s", "1min", "5min"], index=1)

    if st.sidebar.button("🔄 Refresh now"):
        st.cache_data.clear()
        st.rerun()

    if auto_refresh:
        interval_secs = parse_interval(interval_label)
        st.markdown(
            f'<meta http-equiv="refresh" content="{interval_secs}">',
            unsafe_allow_html=True,
        )


def render_export(df: pd.DataFrame):
    if df.empty:
        return
    csv = df.to_csv(index=False)
    st.sidebar.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name="mailjobscan_export.csv",
        mime="text/csv",
    )


def main():
    st.set_page_config(page_title="MailJobScan Dashboard", layout="wide")
    st.title("🔍 MailJobScan Dashboard")
    st.caption("Browse and review analyzed job proposals from your job alert emails.")

    config = load_config()
    db_path = Path(__file__).parent / config["paths"]["db"]

    if not db_path.exists():
        st.warning(f"Database not found at {db_path}. Run the scanner first to populate it.")
        return

    df = load_data(str(db_path))

    with st.sidebar:
        st.header("Filters")
        df = apply_filters(df)
        st.divider()
        render_export(df)
        render_refresh()

    render_stats(df)
    st.divider()
    selected_row = render_table(df)
    if selected_row is not None:
        st.divider()
        render_detail(selected_row)


if __name__ == "__main__":
    main()
