#!/usr/bin/env python3
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from core.engine import refetch_single_job, fetch_single_job
from core.llm.llm_client import LlmClient
from core.storage.repository import JobRepository
from config import load_config

# Repo attribute/column to display name table
COLUMN_DISPLAY_NAMES = {
    "job_title": "Title",
    "company": "Company",
    "location": "Location",
    "salary": "Salary",
    "_best_label": "Total Match",
    "resume_match_level": "Resume Match",
    "expectations_match_level": "Expect. Match",
    "_parsed_date": "Date",
    "id": "ID",
    "resume_match_summary": "Resume Match Summary",
    "expectations_match_summary": "Expectations Match Summary",
    "job_url": "URL",
    "email_subject": "Email Subject",
    "email_from": "Email From",
    "job_technology_domains": "Technology Domains",
    "job_responsibilities_summary": "Responsibilities",
    "job_requirements_summary": "Requirements",
    "commute_info": "Commute Info",
    "status": "Status",
    "notes": "Notes",
}

# helper function
def _strikethrough(val):
    if isinstance(val, str) and val:
        return "\u0336".join(val) + "\u0336"
    return ""

@st.cache_data(ttl=60)
def load_data(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM job_proposals ORDER BY created_at DESC", conn)
    conn.close()

    if df.empty:
        return df

    if "status" not in df.columns:
        df["status"] = "new"
    if "notes" not in df.columns:
        df["notes"] = ""

    df["_parsed_date"] = pd.to_datetime(df["email_received_date"], errors="coerce", utc=True, format="mixed")
    df["_created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True, format="mixed")
    fallback = df["_created_at"].fillna(pd.Timestamp.now(tz="UTC"))
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
        cutoff_start = pd.Timestamp(start, tz="UTC")
        cutoff_end = pd.Timestamp(end, tz="UTC") + timedelta(days=1)
        df = df[(df["_parsed_date"] >= cutoff_start) & (df["_parsed_date"] <= cutoff_end)]
    elif date_filter != "All time":
        days = int(date_filter.split()[1])
        cutoff = pd.Timestamp.now(tz="UTC") - timedelta(days=days)
        df = df[df["_parsed_date"] >= cutoff]

    status_filter = st.sidebar.radio(
        "Status",
        ["All", "New", "Applied", "Interview", "Dismissed"],
        horizontal=True,
    )
    if status_filter != "All":
        status_val = status_filter.lower()
        df = df[df["status"] == status_val]

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


def render_stats(db_path: str):
    df_all = load_data(db_path)
    total = len(df_all)
    high = len(df_all[df_all["_best_label"] == "High"])
    medium = len(df_all[df_all["_best_label"] == "Medium"])
    low = len(df_all[(df_all["_best_label"] == "Low") | (df_all["_best_label"] == "N/A")])

    c1, c2 = st.sidebar.columns(2)
    c1.metric("Total", total)
    c2.metric("🟢 High", high)
    c1.metric("🟠 Medium", medium)
    c2.metric("🔴 Low", low)


def render_table(df: pd.DataFrame):
    if df.empty:
        st.info("No proposals match the selected filters.")
        return None

    match_icon_map = {"High": "🟢", "Medium": "🟠", "Low": "🔴"}

    cols = {
        "job_title": "Job Title",
        "company": "Company",
        "location": "Location",
        "salary": "Salary",
        "status": "Status",
        "_best_label": "Best Match",
        "resume_match_level": "Resume",
        "expectations_match_level": "Expect.",
        "_parsed_date": "Date",
        "id": "ID",
    }
    COLS = [ "job_title", "company", "location", "salary", "status", "_best_label", "resume_match_level", "expectations_match_level", "_parsed_date", "id" ]
    display = df[COLS].copy()
    display["status"] = display["status"].fillna("new").str.capitalize()
    display["_best_label"] = display["_best_label"].map(match_icon_map).fillna("⚪")
    display["_parsed_date"] = (
        pd.to_datetime(display["_parsed_date"], errors="coerce")
        .dt.strftime("%Y-%m-%d")
        .fillna("")
    )

    def _style_dismissed(row):
        if row["status"] == "Dismissed":
            return [
                "color: #999; "
                for _ in range(len(row))
            ]
        return [""] * len(row)

    dismissed_mask = display["status"] == "Dismissed"
    for col in display.columns:
        if col == "status" or display[col].dtype.kind in ("i","f","b"):
            continue
        display.loc[dismissed_mask, col] = display.loc[dismissed_mask, col].apply(_strikethrough)

    styled = display.style.apply(_style_dismissed, axis=1)

    selection = st.dataframe(
        styled,
        column_config={k: COLUMN_DISPLAY_NAMES.get(k,k) for k in COLS},
        on_select="rerun",
        selection_mode="single-row",
        width="stretch",
        hide_index=True,
        height=600,
        key="proposals_table",
    )

    if selection.selection.rows:
        return df.iloc[selection.selection.rows[0]]
    return None


def update_status_in_db(db_path: str, record_id: int, status: str):
    repo = JobRepository(db_path)
    repo.update_status(record_id, status)
    repo.close()

def update_notes_in_db(db_path: str, record_id: int, notes: str):
    repo = JobRepository(db_path)
    repo.update_notes(record_id, notes)
    repo.close()


def _detail_fragment(record_id: int, db_path: str):
    conn = sqlite3.connect(db_path)
    row_df = pd.read_sql(
        "SELECT * FROM job_proposals WHERE id = ?",
        conn, params=(record_id,)
    )
    conn.close()
    if row_df.empty:
        return
    row = row_df.iloc[0]
    row["_parsed_date"] = pd.to_datetime(row["email_received_date"], errors="coerce", utc=True)
    render_detail(row, db_path)

def format_bullets(text: str) -> str:
    #print(f"Formatting bullets for text: {text}")
    if not text or text == "No summary available":
        return "No summary available"
    text = text.strip()
    if "•" in text:
        return text
    parts = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()]
    if len(parts) <= 1:
        return f"- {parts[0]}" if parts else "No summary available"
    return "\n".join(f"- {p}." for p in parts)

def render_detail(row: pd.Series, db_path: str):
    if row is None:
        return

    emoji_map = {"High": "🟢", "Medium": "🟠", "Low": "🔴"}
    r_emoji = emoji_map.get(row["resume_match_level"], "⚪")
    e_emoji = emoji_map.get(row["expectations_match_level"], "⚪")

    left, right = st.columns(2, vertical_alignment="top")

    def cname(col: str) -> str:
        return COLUMN_DISPLAY_NAMES.get(col,col)

    with left:
        st.subheader(f"[{row['job_title']}]({row['job_url']})")
        st.write(f"**{cname('company')}:** {row['company']}")
        st.write(f"**{cname('email_subject')}:** {row['email_subject']}")
        st.write(f"**{cname('email_from')}:** {row['email_from']}")
        st.write(f"**{cname('_parsed_date')}:** {row['_parsed_date'].strftime('%Y-%m-%d %H:%M')}")
        st.write(f"**{cname('salary')}:** {row.get('salary') or 'N/A'}")
        st.write(f"**{cname('location')}:** {row.get('location') or 'N/A'}")
        commute = row.get("commute_info", "")
        if commute:
            st.write(f"**{cname('commute')}:** {commute}")

        resp = row.get("job_responsibilities_summary", "")
        req = row.get("job_requirements_summary", "")
        tech = row.get("job_technology_domains", "")
        if resp or req or tech:
            st.divider()
        if tech:
            st.markdown(f"**{cname('job_technology_domains')}:**")
            st.markdown(tech)
        if resp:
            st.markdown(f"**{cname('job_responsibilities_summary')}:**")
            st.markdown(format_bullets(resp))
        if req:
            st.markdown(f"**{cname('job_requirements_summary')}:**")
            st.markdown(format_bullets(req))


    with right:
        current_status = row.get("status") or "new"
        record_id = int(row["id"])

        def _on_status_change():
            new_val = st.session_state.get(f"status_{record_id}")
            if new_val and new_val != current_status:
                update_status_in_db(db_path, record_id, new_val)
                st.session_state["_selected_id"] = record_id
                st.cache_data.clear()

        st.write(f"**{cname('status')}:**")
        st.selectbox(
            label="status",
            label_visibility="collapsed",
            options=["new", "applied", "interview", "dismissed"],
            index=["new", "applied", "interview", "dismissed"].index(current_status) if current_status in ["new", "applied", "interview", "dismissed"] else 0,
            format_func=lambda x: f"{x.capitalize()}",
            key=f"status_{record_id}",
            on_change=_on_status_change,
        )

        def _on_notes_change():
            new_text = st.session_state.get(f"notes_{record_id}", "")
            if new_text != row.get("notes"):
                update_notes_in_db(db_path, record_id, new_text)
                st.session_state["_selected_id"] = record_id
                st.cache_data.clear()

        st.write(f"**{cname('notes')}:**")
        st.text_area(
            label="notes",
            label_visibility="collapsed",
            value=row.get("notes") or "",
            height=100,
            key=f"notes_{record_id}",
            on_change=_on_notes_change,
        )

        st.divider()

        st.markdown(f"**{cname('resume_match_level')}:** {r_emoji} {row['resume_match_level'] or 'N/A'}")
        st.markdown(format_bullets(row.get("resume_match_summary", "")))
        st.markdown(f"**{cname('expectations_match_level')}:** {e_emoji} {row['expectations_match_level'] or 'N/A'}")
        st.markdown(format_bullets(row.get("expectations_match_summary", "")))

    record_id = int(row["id"])
    job_url = row.get("job_url", "")
    refetch_key = f"refetch_{record_id}"

    if st.session_state.get(refetch_key):
        with st.spinner("Re-fetching job description and re-analyzing..."):
            config = load_config()
            llm = LlmClient(config)
            result = refetch_single_job(job_url, llm, config)
            repo = JobRepository(db_path)
            repo.update_match_results(record_id, result)
            repo.close()
            st.session_state[refetch_key] = False
            st.cache_data.clear()
            st.rerun()

    st.button(
        "🔄 Re-fetch & re-analyze",
        key=f"refetch_btn_{record_id}",
        disabled=st.session_state.get(refetch_key, False),
        on_click=lambda: st.session_state.update({refetch_key: True}),
        type="secondary",
        use_container_width=True,
    )

    if row.get("error"):
        st.warning(f"Error: {row['error']}")


def parse_interval(label: str) -> int:
    return {"15s": 15, "30s": 30, "1min": 60, "5min": 300}[label]


def render_refresh():
    auto_refresh = st.sidebar.toggle("Auto-refresh", value=False)
    interval_label = st.sidebar.selectbox("Interval", ["15s", "30s", "1min", "5min"], index=1)

    if st.sidebar.button("Refresh now"):
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

    # Get all column names from the DataFrame
    all_columns = df.columns.tolist()

    # Filter columns to only those with display names (optional, for cleaner UI)
    displayable_columns = [col for col in all_columns if col in COLUMN_DISPLAY_NAMES]

    # Let the user select columns to export (using format_func to display displayable names)
    selected_columns = st.sidebar.multiselect(
        "Select columns to export",
        options=displayable_columns,
        default=list(COLUMN_DISPLAY_NAMES.keys())[:5],  # Default to first 5 columns
        format_func=lambda x: COLUMN_DISPLAY_NAMES.get(x, x),
    )

    # Rename selected columns to displayable names for CSV export
    df_export = df[selected_columns].rename(columns=COLUMN_DISPLAY_NAMES)

    # Export the renamed DataFrame
    csv = df_export.to_csv(index=False)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"mailjobscanner_export_{timestamp}.csv"

    st.sidebar.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name=file_name,
        mime="text/csv",
    )


@st.dialog("Add Job")
def _add_job_dialog(config: dict, db_path: Path):
    with st.form(key="add_job_form"):
        job_url = st.text_input("Job URL", key="job_url_input")
        submitted = st.form_submit_button(label="Submit")

    if not submitted:
        return
    if not job_url:
        st.warning("Please enter a job URL.")
        return

    with st.spinner("Fetching and analyzing job..."):
        try:
            llm = LlmClient(config)
            repo = JobRepository(str(db_path))
            result = fetch_single_job(job_url, llm, repo, config)
            repo.close()

            if result.get("error"):
                st.error(f"Error: {result['error']}")
                return

            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")


def main():
    config = load_config()
    db_path = Path(__file__).parent / config["paths"]["db"]

    st.set_page_config(page_title="MailJobScanner Dashboard", layout="wide")
    st.title("Job Opportunity Dashboard")
    st.caption(f"Browse and review analyzed job proposals located at {db_path}.")

    if not db_path.exists():
        st.warning(f"Database not found at {db_path}. Run the scanner first to populate it.")
        return

    df = load_data(str(db_path))

    # Add job button
    if st.button("Add Job", key="add_job_button"):
        _add_job_dialog(config, db_path)

    with st.sidebar:
        st.header("📊" + "\u00a0" * 3 + "Analysed jobs")
        render_stats(db_path)
        st.divider()

        st.header("🔍" + "\u00a0" * 3 + "Filters")
        df = apply_filters(df)
        st.divider()

        st.header("🔄" + "\u00a0" * 3 + "Refresh")
        render_refresh()
        st.divider()

        st.header("📥" + "\u00a0" * 3 + " Export")
        render_export(df)

    st.caption(f"📄 **{len(df)}** proposals match the current filters")
    selected_row = render_table(df)
    if selected_row is not None:
        st.session_state["_selected_id"] = int(selected_row["id"])
        st.divider()
        _detail_fragment(st.session_state["_selected_id"], str(db_path))
    elif st.session_state.get("_selected_id") is not None:
        sid = st.session_state["_selected_id"]
        match = df[df["id"] == sid]
        if not match.empty:
            st.divider()
            _detail_fragment(sid, str(db_path))
        else:
            st.session_state.pop("_selected_id", None)

if __name__ == "__main__":
    main()
