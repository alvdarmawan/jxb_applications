#!/usr/bin/env python3
"""
Import a CSV export of the job-application Google Sheet into SQLite.

Usage:
    python import_applications.py applications.csv --db jxb_applications.db
    python import_applications.py applications.csv --db jxb_applications.db --links links.csv

If --links is omitted, three default links (LinkedIn, GitHub, Overleaf resume)
are seeded as placeholders -- edit them directly in the DB or pass a real CSV.
"""

import argparse
import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

VALID_STAGES = {
    "applied", "assessment", "interview",
    "offer", "accepted", "rejected", "withdrawn",
}

# Maps a handful of likely header spellings -> our canonical field name.
# Add alternates here if your export uses slightly different headers.
HEADER_ALIASES = {
    "date": "date_applied",
    "date applied": "date_applied",
    "deadline": "deadline",
    "company": "company",
    "priority": "priority",
    "stage/status": "stage",
    "stage": "stage",
    "status": "stage",
    "role": "role",
    "location": "location",
    "url": "url",
    # "application age" is intentionally skipped -- it's computed, not stored.
}

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y"]


def parse_date(value: str):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    print(f"  ! Could not parse date '{value}', leaving blank", file=sys.stderr)
    return None


def normalize_headers(fieldnames):
    mapping = {}
    for raw in fieldnames:
        key = raw.strip().lower()
        if key in HEADER_ALIASES:
            mapping[raw] = HEADER_ALIASES[key]
    return mapping


def import_applications(csv_path: Path, conn: sqlite3.Connection):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header_map = normalize_headers(reader.fieldnames)
        missing = {"company", "role", "stage"} - set(header_map.values())
        if missing:
            sys.exit(f"CSV is missing required column(s): {', '.join(missing)}")

        inserted, skipped = 0, 0
        cur = conn.cursor()

        for row_num, row in enumerate(reader, start=2):  # row 1 = header
            data = {header_map[k]: v for k, v in row.items() if k in header_map}

            company = (data.get("company") or "").strip()
            role = (data.get("role") or "").strip()
            stage_raw = (data.get("stage") or "").strip()

            if not company or not role:
                print(f"  ! Row {row_num}: missing company/role, skipping")
                skipped += 1
                continue

            stage_lookup = stage_raw.lower()
            if stage_lookup not in VALID_STAGES:
                print(f"  ! Row {row_num}: unrecognized stage '{stage_raw}', skipping")
                skipped += 1
                continue
            stage = stage_lookup.capitalize() if stage_lookup != "withdrawn" else "Withdrawn"
            # capitalize() mangles multi-word stages fine here since all are single words

            priority_raw = (data.get("priority") or "").strip()
            priority = int(priority_raw) if priority_raw in {"1", "2", "3"} else None

            cur.execute(
                """
                INSERT INTO applications
                    (company, role, date_applied, deadline, priority, stage, location, url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company,
                    role,
                    parse_date(data.get("date_applied")),
                    parse_date(data.get("deadline")),
                    priority,
                    stage,
                    (data.get("location") or "").strip() or None,
                    (data.get("url") or "").strip() or None,
                ),
            )
            inserted += 1

        conn.commit()
        print(f"\nDone: {inserted} rows inserted, {skipped} rows skipped.")


def import_links(csv_path: Path, conn: sqlite3.Connection):
    cur = conn.cursor()
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            label = (row.get("label") or row.get("Label") or "").strip()
            url = (row.get("url") or row.get("URL") or "").strip()
            if label and url:
                cur.execute("INSERT INTO links (label, url) VALUES (?, ?)", (label, url))
                count += 1
    conn.commit()
    print(f"Imported {count} links.")


def seed_default_links(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM links")
    if cur.fetchone()[0] > 0:
        return  # don't duplicate on re-runs
    defaults = [
        ("LinkedIn", "https://linkedin.com/in/alvdarmawan"),
        ("GitHub", "https://github.com/alvdarmawan"),
        ("Resume (Overleaf)", "https://overleaf.com/project"),
    ]
    cur.executemany("INSERT INTO links (label, url) VALUES (?, ?)", defaults)
    conn.commit()
    print("Seeded 3 placeholder links -- update these with your real URLs.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("applications_csv", type=Path, help="CSV export of the applications sheet")
    parser.add_argument("--db", type=Path, default=Path("jxb_applications.db"), help="SQLite DB file to create/use")
    parser.add_argument("--links", type=Path, default=None, help="Optional CSV with 'label,url' columns")
    parser.add_argument("--schema", type=Path, default=Path("schema.sql"), help="Path to schema.sql")
    args = parser.parse_args()

    if not args.applications_csv.exists():
        sys.exit(f"File not found: {args.applications_csv}")

    conn = sqlite3.connect(args.db)
    conn.executescript(args.schema.read_text())

    print(f"Importing applications from {args.applications_csv} ...")
    import_applications(args.applications_csv, conn)

    if args.links and args.links.exists():
        print(f"\nImporting links from {args.links} ...")
        import_links(args.links, conn)
    else:
        seed_default_links(conn)

    conn.close()
    print(f"\nDatabase ready at: {args.db}")


if __name__ == "__main__":
    main()
