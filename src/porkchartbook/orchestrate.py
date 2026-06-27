#!/usr/bin/env python3
"""
orchestrate.py — daily pork chartbook run.

One unattended pass, designed to be driven by launchd via
update_pork_chartbook.sh:

  1. For each source in the manifest:
       - daily drivers (AMS hog/cutout, FRED) are always ingested.
       - long-term sources are checked with a cheap freshness probe and
         re-ingested only when the probe shows the source published something
         new (NASS, ERS). Cheap-endpoint long-term sources (AMS retail, Comex)
         are fetched directly and change is detected from row deltas.
     Each source runs isolated — one failure never aborts the others.
  2. If any source produced new/updated data, rebuild docs/data.json,
     commit it, and push to GitHub.
  3. Email a summary every run: what updated, long-term changes flagged,
     and any errors (pulled from this run's results + etl_log).

Usage:
  python -m porkchartbook.orchestrate                 # full daily run
  python -m porkchartbook.orchestrate --dry-run       # do everything except
                                                       #   commit/push/send email
  python -m porkchartbook.orchestrate --no-push       # ingest+build+email, no git push
  python -m porkchartbook.orchestrate --no-email      # skip the email
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date

from . import build_dashboard
from . import db
from . import ingest
from . import notify
from . import probes
from .paths import DEFAULT_DB_PATH, DOCS_ROOT, REPO_ROOT

DATA_JSON_REL = "docs/data.json"
LOCK_PATH = REPO_ROOT / ".orchestrate.lock"


# ── Source manifest ─────────────────────────────────────────────────────────
#
# tier        "daily"     → always ingest (short-term driver)
#             "long-term" → check before ingesting
# probe       callable(conn=None) -> probes.ProbeResult, or None.
#             When None, the source is ingested every run (its endpoint is
#             cheap) and change is detected purely from the row delta.
# fingerprint list of (table, date_col, where) summed/maxed before & after
#             ingest to measure what actually landed.

SOURCES = [
    {
        "key": "ams_hog",
        "label": "USDA AMS hog price & cutout (daily)",
        "label_short": "AMS hog/cutout",
        "tier": "daily",
        "probe": None,
        "ingest": ingest.update_ams,
        "fingerprint": [("ams_hog_prices", "report_date", None)],
    },
    {
        "key": "fred",
        "label": "FRED feed/retail proxies",
        "label_short": "FRED",
        "tier": "daily",
        "probe": None,
        "ingest": ingest.backfill_fred,
        "fingerprint": [("fred_series", "observation_date", None)],
    },
    {
        "key": "ams_retail",
        "label": "AMS weekly retail pork feature activity",
        "label_short": "AMS retail",
        "tier": "long-term",
        "probe": None,  # MyMarketNews endpoint is cheap; fetch + detect delta
        "ingest": ingest.update_retail,
        "fingerprint": [("retail_metrics", "report_date", None)],
    },
    {
        "key": "comex",
        "label": "Brazil pork exports (MDIC/SECEX Comex Stat)",
        "label_short": "Brazil/Comex",
        "tier": "long-term",
        "probe": None,  # API call is the fetch; detect delta
        "ingest": ingest.update_comexstat,
        "fingerprint": [("comexstat_pork_exports", "report_month", "flow = 'export'")],
    },
    {
        "key": "census_trade",
        "label": "US pork trade by HS, product weight (US Census)",
        "label_short": "Census trade",
        "tier": "long-term",
        "probe": None,  # API call is the fetch; detect delta (no-ops without key)
        "ingest": ingest.update_census,
        "fingerprint": [("census_pork_trade", "report_month", "flow = 'export'")],
    },
    {
        "key": "ers_food_avail",
        "label": "ERS per-capita pork availability & disappearance",
        "label_short": "ERS food avail",
        "tier": "long-term",
        "probe": None,  # cheap CSV; detect new year from the row delta
        "ingest": ingest.ingest_ers_food_availability,
        "fingerprint": [("ers_food_availability", "year", "commodity = 'pork'")],
    },
    {
        "key": "wasde",
        "label": "USDA WASDE pork forecasts (production, exports, hog price)",
        "label_short": "WASDE",
        "tier": "long-term",
        "probe": None,  # small monthly text file; detect new vintage from the delta
        "ingest": ingest.ingest_wasde,
        "fingerprint": [("wasde_forecasts", "report_month", None)],
    },
    {
        "key": "fas_psd",
        "label": "FAS PSD world pork production & exports by country",
        "label_short": "FAS PSD",
        "tier": "long-term",
        "probe": None,  # ~1 MB bulk CSV; detect a new market year from the delta
        "ingest": ingest.ingest_psd,
        "fingerprint": [("fas_psd_pork", "market_year", None)],
    },
    {
        "key": "ers_price_spreads",
        "label": "ERS Meat Price Spreads (pork farm/wholesale/retail)",
        "label_short": "ERS spreads",
        "tier": "long-term",
        "probe": None,  # monthly CSV; detect a new month from the delta
        "ingest": ingest.ingest_ers_price_spreads,
        "fingerprint": [("ers_price_spreads", "report_month", None)],
    },
    {
        "key": "nass",
        "label": "USDA NASS (hogs & pigs, slaughter, cold storage)",
        "label_short": "NASS",
        "tier": "long-term",
        "probe": probes.nass_probe,
        "ingest": ingest.update_nass,
        "fingerprint": [("nass_data", "load_time", None)],
    },
    {
        "key": "ers_trade",
        "label": "USDA ERS monthly pork trade",
        "label_short": "ERS trade",
        "tier": "long-term",
        "probe": probes.ers_probe,
        "ingest": ingest.update_ers,
        "fingerprint": [
            ("ers_trade_totals", "report_month", "commodity = 'pork'"),
            ("ers_trade_partner_country", "report_month", "commodity = 'pork'"),
        ],
    },
]


# ── Fingerprints ─────────────────────────────────────────────────────────--

def _fingerprint(conn, specs):
    """Combine (count, max_date) across one or more table specs."""
    total = 0
    max_date = None
    for table, date_col, where in specs:
        count, mx = db.table_fingerprint(conn, table, date_col, where)
        total += count
        if mx is not None and (max_date is None or str(mx) > str(max_date)):
            max_date = mx
    return (total, max_date)


# ── Per-source run ───────────────────────────────────────────────────────--

def _run_source(conn, src):
    """Run one source. Returns a result dict for the email/report."""
    key = src["key"]
    result = {
        "key": key,
        "label": src["label"],
        "label_short": src["label_short"],
        "tier": src["tier"],
        "action": None,
        "new_rows": 0,
        "changed": False,
        "latest_date": None,
        "note": "",
        "error": None,
    }

    before = _fingerprint(conn, src["fingerprint"])

    # ── Decide whether to ingest ──
    should_ingest = True
    if src["probe"] is not None:
        try:
            pr = src["probe"]()
        except Exception as exc:  # noqa: BLE001 — probe must never abort the run
            pr = probes.ProbeResult(value=None, ok=False, note=f"probe raised: {exc}")

        prev = db.get_source_state(conn, key)
        if not pr.ok:
            # Fail safe: probe couldn't confirm, so ingest rather than risk
            # silently missing a real update.
            should_ingest = True
            result["action_hint"] = "probe-error"
            result["error"] = f"probe error: {pr.note}"
            db.log_fetch(conn, key, str(date.today()), str(date.today()), 0,
                         data_item="probe", status="error")
        elif prev is None:
            should_ingest = True  # never probed before
        elif pr.value != prev:
            should_ingest = True  # source published something new
        else:
            should_ingest = False  # unchanged → skip the heavy ingest

        result["note"] = pr.note
        if pr.value is not None:
            db.set_source_state(conn, key, pr.value,
                                changed=(prev is not None and pr.value != prev))

    # ── Ingest (or skip) ──
    if not should_ingest:
        result["action"] = "skipped"
        result["latest_date"] = before[1]
        return result

    try:
        src["ingest"](conn)
    except Exception as exc:  # noqa: BLE001
        result["action"] = "error"
        result["error"] = str(exc)
        db.log_fetch(conn, key, str(date.today()), str(date.today()), 0, status="error")
        return result

    after = _fingerprint(conn, src["fingerprint"])
    # Keep "probe-error" so the email shows we ingested as a fail-safe; otherwise
    # this was a clean ingest.
    result["action"] = "probe-error" if result.get("action_hint") == "probe-error" else "ingested"
    result["new_rows"] = max(0, after[0] - before[0])
    result["changed"] = after != before
    result["latest_date"] = after[1]
    return result


# ── Git ──────────────────────────────────────────────────────────────────--

def _git(args, check=False):
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True, text=True, check=check,
    )


def _sync_with_origin():
    """Pull origin/main before building so the data commit lands on top of the
    latest (e.g. frontend) work and the later push fast-forwards instead of
    failing non-fast-forward.

    docs/data.json is a regenerated artifact: if a prior run committed it but
    couldn't push (diverging the branch), those local-ahead commits are safe to
    discard and rebuild on top of origin. We only auto-reset when every
    local-ahead change is docs/data.json; anything else is left for a human.
    Returns a short status note (None == cleanly synced).
    """
    if _git(["fetch", "origin", "main"]).returncode != 0:
        return "fetch failed; building on local HEAD"
    # Up to date or simply behind → fast-forward.
    if _git(["merge", "--ff-only", "origin/main"]).returncode == 0:
        return None
    # Diverged. Inspect what the local-ahead commits actually touched.
    changed = _git(["diff", "--name-only", "origin/main...HEAD"]).stdout.split()
    if changed and all(path == DATA_JSON_REL for path in changed):
        _git(["reset", "--hard", "origin/main"])
        return "reset stale local data.json commit onto origin"
    return f"diverged with non-data commits ({', '.join(changed) or '?'}); manual reconcile needed"


def _commit_and_push(date_str, no_push=False):
    """Commit docs/data.json ONLY, optionally push.

    Deliberately path-scoped: the job never touches, reverts, or commits any
    other file. It compares the working tree to HEAD for docs/data.json (so the
    check is independent of whatever else you have staged), and commits with an
    explicit pathspec — any other files you have modified or staged locally are
    left exactly as they are. Returns (committed, commit_hash, diff_stat, error).
    """
    # Has docs/data.json actually changed vs the last commit? (index-independent)
    if _git(["diff", "--quiet", "HEAD", "--", DATA_JSON_REL]).returncode == 0:
        return (False, None, "", None)  # no change to data.json
    diff_stat = _git(["diff", "--stat", "HEAD", "--", DATA_JSON_REL]).stdout.strip()

    # Pathspec-scoped commit: commits the working-tree docs/data.json and nothing
    # else, regardless of what is staged in the index.
    commit = _git(["commit", "-m", f"Update pork chartbook data — {date_str}", "--", DATA_JSON_REL])
    if commit.returncode != 0:
        return (False, None, diff_stat, commit.stderr.strip() or commit.stdout.strip())

    rev = _git(["rev-parse", "--short", "HEAD"])
    commit_hash = rev.stdout.strip()

    if no_push:
        return (True, commit_hash, diff_stat, None)

    push = _git(["push", "origin", "main"])
    if push.returncode != 0:
        return (True, commit_hash, diff_stat, f"push failed: {push.stderr.strip()}")
    return (True, commit_hash, diff_stat, None)


# ── Lock ─────────────────────────────────────────────────────────────────--

def _acquire_lock():
    try:
        fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _release_lock():
    try:
        os.unlink(str(LOCK_PATH))
    except FileNotFoundError:
        pass


# ── Main ─────────────────────────────────────────────────────────────────--

def run(dry_run=False, no_push=False, no_email=False, db_path=None):
    date_str = date.today().strftime("%B %d, %Y")
    conn = db.init_db(db_path or DEFAULT_DB_PATH)

    report = {
        "date_str": date_str,
        "sources": [],
        "build_ok": True,
        "build_note": "",
        "data_changed": False,
        "pushed": False,
        "commit": None,
        "diff_stat": "",
        "dry_run": dry_run,
        "sync_note": None,
    }

    # Pull origin/main up front (unless this is a dry run that must not touch the
    # tree) so the data commit builds on the latest and pushes cleanly.
    if not dry_run:
        report["sync_note"] = _sync_with_origin()
        if report["sync_note"]:
            print(f"\n[sync] {report['sync_note']}")

    try:
        for src in SOURCES:
            print(f"\n>>> {src['label']}")
            res = _run_source(conn, src)
            report["sources"].append(res)
            print(f"    action={res['action']} new_rows={res['new_rows']} "
                  f"changed={res['changed']} note={res['note']!r} error={res['error']!r}")

        data_changed = any(s["changed"] for s in report["sources"])
        report["data_changed"] = data_changed

        # ── Rebuild + publish only when something actually changed ──
        if data_changed:
            try:
                build_dashboard.build_data_json(conn)
            except Exception as exc:  # noqa: BLE001
                report["build_ok"] = False
                report["build_note"] = str(exc)
                print(f"  BUILD FAILED: {exc}", file=sys.stderr)

            if report["build_ok"] and not dry_run:
                committed, commit_hash, diff_stat, git_err = _commit_and_push(date_str, no_push=no_push)
                report["pushed"] = committed and not no_push and git_err is None
                report["commit"] = commit_hash
                report["diff_stat"] = diff_stat
                if git_err:
                    report["sources"].append({
                        "key": "git", "label": "Git push", "label_short": "git",
                        "tier": "daily", "action": "error", "new_rows": 0,
                        "changed": False, "latest_date": None, "note": "", "error": git_err,
                    })
            elif report["build_ok"] and dry_run:
                # Show what would have been published.
                diff = _git(["diff", "--stat", "--", DATA_JSON_REL])
                report["diff_stat"] = diff.stdout.strip()
        else:
            print("\nNo source changed — skipping rebuild/commit/push.")
    finally:
        conn.close()

    # ── Email (always) ──
    subject, body = notify.build_summary(report)
    print("\n" + "=" * 70)
    print(subject)
    print("=" * 70)
    if not no_email:
        notify.send_email(subject, body, dry_run=dry_run)
    else:
        print(body)

    return report


def main():
    ap = argparse.ArgumentParser(description="Daily pork chartbook orchestrator")
    ap.add_argument("--dry-run", action="store_true",
                    help="Ingest + build, but do not commit/push or send email")
    ap.add_argument("--no-push", action="store_true", help="Commit but do not push")
    ap.add_argument("--no-email", action="store_true", help="Do not send the summary email")
    ap.add_argument("--db", default=None, help="Path to SQLite database file")
    args = ap.parse_args()

    if not _acquire_lock():
        print(f"Another run holds {LOCK_PATH}; exiting.", file=sys.stderr)
        sys.exit(0)
    try:
        report = run(dry_run=args.dry_run, no_push=args.no_push,
                     no_email=args.no_email, db_path=args.db)
    finally:
        _release_lock()

    # Non-zero exit if any source or the build errored (visible to launchd log).
    had_error = (not report["build_ok"]) or any(s["error"] for s in report["sources"])
    sys.exit(1 if had_error else 0)


if __name__ == "__main__":
    main()
