#!/usr/bin/env python3
"""
notify.py — compose and send the daily pork chartbook run summary email.

Mirrors the HPAI dashboard convention: plain-text email over Gmail SMTP using
the GMAIL_APP_PASSWORD environment variable. The orchestrator hands this module
a structured run report; this module turns it into a subject + body and sends.

Report shape (built by orchestrate.py):
    {
      "date_str": "June 12, 2026",
      "sources":  [ {key,label,tier,action,new_rows,changed,latest_date,note,error}, ... ],
      "build_ok": bool, "build_note": str,
      "pushed":   bool, "commit": str|None, "diff_stat": str,
      "dry_run":  bool,
    }

A source dict:
    tier    : "daily" | "long-term"
    action  : "ingested" | "skipped" | "probe-error" | "error"
    changed : True when new/updated rows actually landed
"""

from __future__ import annotations

import os
import smtplib
import sys
from email.mime.text import MIMEText

FROM_ADDR = "casey.m.downey@gmail.com"
TO_ADDRS = ["casey@innovateanimalag.org"]


# ── Helpers ────────────────────────────────────────────────────────────────

def _long_term_changes(report):
    return [
        s for s in report["sources"]
        if s["tier"] == "long-term" and s["changed"]
    ]


def _errors(report):
    errs = [s for s in report["sources"] if s["error"]]
    if not report["build_ok"]:
        errs = errs + [{"label": "Dashboard build", "error": report.get("build_note", "build failed")}]
    return errs


def _fmt_source_line(s):
    bits = []
    if s["new_rows"]:
        bits.append(f"+{s['new_rows']:,} rows")
    if s["latest_date"]:
        bits.append(f"through {s['latest_date']}")
    if s["note"]:
        bits.append(s["note"])
    detail = "; ".join(bits) if bits else "no change"
    return f"  - {s['label']}: {detail}"


# ── Public API ───────────────────────────────────────────────────────────--

def build_summary(report):
    """Return (subject, body) for the run report."""
    date_str = report["date_str"]
    flagged = _long_term_changes(report)
    errors = _errors(report)
    daily = [s for s in report["sources"] if s["tier"] == "daily"]
    long_term = [s for s in report["sources"] if s["tier"] == "long-term"]

    # ── Subject ──
    prefix = "[DRY RUN] " if report.get("dry_run") else ""
    if errors:
        subject = f"{prefix}⚠️ Pork chartbook update had errors — {date_str}"
    elif flagged:
        names = ", ".join(s["label_short"] for s in flagged)
        subject = f"{prefix}\U0001f514 Pork chartbook: {names} updated — {date_str}"
    elif report.get("data_changed"):
        subject = f"{prefix}Pork chartbook updated — {date_str}"
    else:
        subject = f"{prefix}Pork chartbook — no changes — {date_str}"

    # ── Body ──
    lines = []
    lines.append(f"Pork Industry Executive Chartbook — daily update for {date_str}")
    lines.append("")

    if report.get("dry_run"):
        lines.append("(DRY RUN — no commit/push/email was performed in the actual run path.)")
        lines.append("")

    # Headline: push status
    if not report["build_ok"]:
        lines.append("Status: BUILD FAILED — dashboard data.json was not rebuilt.")
    elif report["pushed"]:
        commit = report.get("commit") or "(unknown)"
        lines.append(f"Status: data.json rebuilt, committed ({commit}) and pushed to GitHub.")
    elif report.get("data_changed") and report.get("dry_run"):
        lines.append("Status: data.json rebuilt; would commit + push (dry run — not performed).")
    elif report.get("data_changed"):
        lines.append("Status: data.json rebuilt; NOT pushed (see errors / --no-push).")
    else:
        lines.append("Status: no data changed; nothing rebuilt or pushed.")
    lines.append("")

    # Flagged long-term updates — the part Casey most wants surfaced.
    if flagged:
        lines.append("\U0001f514 LONG-TERM DATA UPDATED (not a daily driver):")
        for s in flagged:
            lines.append(_fmt_source_line(s))
        lines.append("")

    # Daily drivers
    lines.append("Daily drivers:")
    for s in daily:
        lines.append(_fmt_source_line(s))
    lines.append("")

    # Long-term sources checked
    lines.append("Long-term sources checked today:")
    for s in long_term:
        status = {
            "ingested": "UPDATED" if s["changed"] else "ingested (no new rows)",
            "skipped": "no new data (skipped ingest)",
            "probe-error": "PROBE ERROR — ingested as fail-safe",
            "error": "ERROR",
        }.get(s["action"], s["action"])
        line = f"  - {s['label']}: {status}"
        if s["new_rows"]:
            line += f" (+{s['new_rows']:,} rows)"
        lines.append(line)
    lines.append("")

    # Errors
    if errors:
        lines.append("⚠️ ERRORS:")
        for e in errors:
            lines.append(f"  - {e['label']}: {e['error']}")
        lines.append("")

    # Git diff stat
    if report.get("diff_stat"):
        lines.append("Git changes:")
        lines.append(report["diff_stat"])
        lines.append("")

    return subject, "\n".join(lines).rstrip() + "\n"


def send_email(subject, body, to_addrs=None, dry_run=False):
    """Send the summary over Gmail SMTP. No-ops (prints) if creds are missing
    or dry_run is set."""
    to_addrs = to_addrs or TO_ADDRS
    if dry_run:
        print("── EMAIL (dry run, not sent) ──")
        print(f"To: {', '.join(to_addrs)}")
        print(f"Subject: {subject}")
        print(body)
        return True

    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not password:
        print("WARNING: GMAIL_APP_PASSWORD not set, skipping email", file=sys.stderr)
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = FROM_ADDR
    msg["To"] = ", ".join(to_addrs)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(FROM_ADDR, password)
            server.send_message(msg)
        print(f"Email sent: {subject}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Email failed: {exc}", file=sys.stderr)
        return False
