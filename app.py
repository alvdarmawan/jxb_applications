"""
Jxb Application Tracker - Streamlit

Run with:
    streamlit run app.py

Expects jxb_applications.db (created by import_applications.py) in the same folder.
"""

import sqlite3
from datetime import date

import pandas as pd
import streamlit as st

DB_PATH = "jxb_applications.db"

STAGES = ["Applied", "Assessment", "Interview", "Offer", "Accepted", "Rejected", "Withdrawn"]

st.set_page_config(page_title="Jxb Application Tracker", layout="wide")


def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def load_applications(conn) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM applications", conn)
    if df.empty:
        return df

    today = pd.Timestamp(date.today())
    df["date_applied"] = pd.to_datetime(df["date_applied"], errors="coerce")
    df["deadline"] = pd.to_datetime(df["deadline"], errors="coerce")

    # Computed, not stored -- always current. Do this BEFORE converting to
    # plain dates below, since Timestamp math is what makes .dt.days work.
    df["days_since_applied"] = (today - df["date_applied"]).dt.days
    df["days_until_deadline"] = (df["deadline"] - today).dt.days

    # Convert to plain dates for display, now that the math above is done.
    df["date_applied"] = df["date_applied"].dt.date
    df["deadline"] = df["deadline"].dt.date

    return df


def format_days_until(x):
    """Turn a days-until-deadline number into something readable in the table."""
    if pd.isna(x):
        return "-"
    elif x < 0:
        return "Past due"
    else:
        return int(x)


def format_days_since(x):
    if pd.isna(x) or x < 0:
        return "-"
    else:
        return int(x)


def add_application(conn, company, role, date_applied, deadline, priority, stage, location, url):
    conn.execute(
        """
        INSERT INTO applications (company, role, date_applied, deadline, priority, stage, location, url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company.strip(),
            role.strip(),
            date_applied.isoformat() if date_applied else None,
            deadline.isoformat() if deadline else None,
            priority,
            stage,
            location.strip() or None,
            url.strip() or None,
        ),
    )
    conn.commit()


def update_application(conn, row_id, company, role, date_applied, deadline, priority, stage, location, url):
    conn.execute(
        """
        UPDATE applications
        SET company = ?, role = ?, date_applied = ?, deadline = ?,
            priority = ?, stage = ?, location = ?, url = ?
        WHERE id = ?
        """,
        (
            company,
            role,
            date_applied.isoformat() if pd.notna(date_applied) else None,
            deadline.isoformat() if pd.notna(deadline) else None,
            priority,
            stage,
            location,
            url,
            int(row_id),
        ),
    )


def main():
    conn = get_connection()

    st.title("Jxb Application Tracker")

    with st.expander("➕ Add new application"):
        with st.form("add_application_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                company = st.text_input("Company")
                role = st.text_input("Role")
                location = st.text_input("Location")
                url = st.text_input("URL")
            with col2:
                date_applied = st.date_input("Date applied", value=date.today())
                deadline = st.date_input("Deadline (optional)", value=None)
                priority = st.selectbox("Priority", [1, 2, 3], index=1)
                stage = st.selectbox("Stage", STAGES)

            submitted = st.form_submit_button("Add")
            if submitted:
                if not company or not role:
                    st.error("Company and Role are required.")
                else:
                    add_application(conn, company, role, date_applied, deadline, priority, stage, location, url)
                    st.success(f"Added {company} - {role}")
                    st.rerun()

    df = load_applications(conn)

    if df.empty:
        st.info("No applications yet. Add one above, or run import_applications.py to bring in your data.")
        return

    st.subheader("Filters")
    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        stage_filter = st.multiselect("Stage", STAGES, default=[])
    with fcol2:
        priority_filter = st.multiselect("Priority", [1, 2, 3], default=[])

    filtered = df.copy()
    if stage_filter:
        filtered = filtered[filtered["stage"].isin(stage_filter)]
    if priority_filter:
        filtered = filtered[filtered["priority"].isin(priority_filter)]

    st.subheader(f"Applications ({len(filtered)})")
    st.caption("Stage and Priority are editable directly in the table below. Click 'Save changes' when done.")

    display_cols = [
        "id", "company", "role", "stage", "priority", "location",
        "date_applied", "deadline", "days_since_applied", "days_until_deadline", "url",
    ]
    filtered_display = filtered[display_cols].sort_values(
        by="days_until_deadline", na_position="last"
    ).reset_index(drop=True)

    # Keep an unformatted copy to compare against after editing, and a
    # formatted copy for display (so "Past due" etc. show in the table).
    original = filtered_display.copy()
    filtered_display["days_since_applied"] = filtered_display["days_since_applied"].apply(format_days_since)
    filtered_display["days_until_deadline"] = filtered_display["days_until_deadline"].apply(format_days_until)

    edited_df = st.data_editor(
        filtered_display,
        column_config={
            "id": None,  # hide the id column, but keep it in the data for saving
            "company": st.column_config.Column("Company"),
            "role": st.column_config.Column("Role"),
            "stage": st.column_config.SelectboxColumn("Stage", options=STAGES, required=True),
            "priority": st.column_config.SelectboxColumn("Priority", options=[1, 2, 3], required=True),
            "location": st.column_config.Column("Location"),
            "date_applied": st.column_config.DateColumn("Date Applied"),
            "deadline": st.column_config.DateColumn("Deadline"),
            "days_since_applied": st.column_config.Column("Days Since Applied"),
            "days_until_deadline": st.column_config.Column("Days Until Deadline"),
            "url": st.column_config.Column("URL"),
        },
        disabled=["days_since_applied", "days_until_deadline"],  # computed -- editing them would be undone on refresh
        hide_index=True,
        use_container_width=True,
        key="applications_editor",
    )

    editable_fields = ["company", "role", "date_applied", "deadline", "priority", "stage", "location", "url"]

    if st.button("💾 Save changes"):
        changed = 0
        for _, row in edited_df.iterrows():
            original_row = original[original["id"] == row["id"]].iloc[0]
            if any(row[field] != original_row[field] for field in editable_fields):
                update_application(
                    conn, row["id"], row["company"], row["role"], row["date_applied"],
                    row["deadline"], row["priority"], row["stage"], row["location"], row["url"],
                )
                changed += 1
        conn.commit()
        if changed:
            st.success(f"Updated {changed} row(s).")
            st.rerun()
        else:
            st.info("No changes to save.")

    st.subheader("At a glance")
    m1, m2, m3 = st.columns(3)
    m1.metric("Total applications", len(df))
    m2.metric("Active (not closed out)", int(df["stage"].isin(["Applied", "Assessment", "Interview"]).sum()))
    upcoming = df[(df["days_until_deadline"].notna()) & (df["days_until_deadline"].between(0, 7))]
    m3.metric("Deadlines in next 7 days", len(upcoming))


if __name__ == "__main__":
    main()
