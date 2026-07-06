#!/usr/bin/env python3
"""
NRC Crux (crossword) tracker
----------------------------
NRC's puzzles run on the 42puzzles / q42 platform. Your individual solve
*time* is stored only in the browser (localStorage) — the server keeps just
aggregates + a per-date finished/not-finished flag. So this tracker is built
around the binary "did I solve it" signal, which IS server-side and needs no
login (your playerId/userId are stable capability tokens). That makes it safe
to run unattended (e.g. a daily GitHub Action).

Server-side, write-free source (one GET):
    https://api.42puzzles.com/hub/nrc/overview?userId=<NRC_USER_ID>
  -> the Crux entry gives today's status, a per-date `completed` history
     (everything since the last stats snapshot), and aggregate stats.

Output:
    data/crux_scores.csv   one row per date: solved (bool) + puzzle metadata
    data/crux_stats.json   snapshot of current aggregates + streaks

Optional: pass --dump <crux_storage_dump.json> (a browser storage export, see
tools/crux_export_snippet.js) to additionally fill in your solve *time* for the
dates that export still holds (~last week), plus that puzzle's global average.

Usage:
    python scripts/fetch_nrc.py              # server-only: solved flags + stats
    python scripts/fetch_nrc.py --dump ~/Downloads/crux_storage_dump.json
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    print("Missing dependency: run  pip install requests")
    sys.exit(1)

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass


API_BASE      = "https://api.42puzzles.com"
OVERVIEW_URL  = f"{API_BASE}/hub/nrc/overview"
ENDSCREEN_URL = f"{API_BASE}/hub/nrc/endscreen"
RATE_DELAY    = 0.25
HEADERS = {
    "Origin":  "https://www.nrc.nl",
    "Referer": "https://www.nrc.nl/",
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}

FIELDNAMES = [
    "date", "puzzle_id", "puzzle_type",
    "constructor", "width", "height",
    "solved",
    "seconds", "time",
    "global_avg_seconds", "global_avg_time",
]


def format_time(seconds) -> str:
    if seconds in (None, ""):
        return ""
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def ymd_to_date(ymd: str) -> str:
    return datetime.strptime(ymd, "%Y%m%d").strftime("%Y-%m-%d")


def fetch_overview(session: requests.Session, user_id: str, player_id: str) -> dict:
    """GET the gameshub overview and return this player's Crux entry."""
    resp = session.get(OVERVIEW_URL, params={"userId": user_id},
                       headers=HEADERS, timeout=30)
    resp.raise_for_status()
    puzzles = resp.json().get("puzzles", []) or []
    target = f"nrc-{player_id}"
    for p in puzzles:
        if p.get("playerId") == target or (
            p.get("renderer") == "crossword" and p.get("name") == "Crux"
        ):
            return p
    raise SystemExit("Could not find the Crux entry in the overview "
                     "(check NRC_PLAYER_ID).")


def fetch_metadata(session: requests.Session, player_id: str, date: str) -> dict | None:
    """Puzzle metadata for a date; None if no puzzle that day (404)."""
    try:
        resp = session.get(f"{API_BASE}/player/nrc/{player_id}",
                           params={"date": date}, headers=HEADERS, timeout=30)
        if resp.status_code in (403, 404):
            return None
        resp.raise_for_status()
        data = resp.json()
        puzzle = data.get("puzzle", {}) or {}
        return {
            "puzzle_id":   data.get("puzzleId", ""),
            "constructor": puzzle.get("origin", ""),
            "width":       puzzle.get("width", ""),
            "height":      puzzle.get("height", ""),
        }
    except (requests.RequestException, ValueError):
        return None


def fetch_global_avg(session, player_id, user_id, puzzle_id, date, play_ms):
    """Duplicate-safe replay of a real recorded time -> that puzzle's global avg."""
    body = {
        "brandId": "nrc", "playerId": player_id, "userId": user_id,
        "puzzleId": puzzle_id, "puzzleDate": date,
        "currentGame": {
            "playerId": f"nrc-{player_id}", "completed": True,
            "userCheated": False, "gameType": "crossword",
            "playTime": play_ms, "completedInPreviousSession": True,
        },
    }
    try:
        resp = session.post(ENDSCREEN_URL, json=body, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        avg_ms = (resp.json().get("globalStats", {}) or {}).get("avgTime")
        return round(avg_ms / 1000) if avg_ms else ""
    except (requests.RequestException, ValueError):
        return ""


def parse_dump_times(path: str, player_id: str) -> dict[str, dict]:
    """date -> {play_ms, puzzle_id} from a browser storage export (optional)."""
    out = {}
    try:
        with open(path) as f:
            dump = json.load(f)
    except (OSError, json.JSONDecodeError):
        print(f"  (could not read dump {path}; skipping time enrichment)")
        return out
    prefix = f"save-nrc-{player_id}-"
    for key, raw in (dump.get("localStorage", {}) or {}).items():
        if not key.startswith(prefix):
            continue
        try:
            value = json.loads(raw)
            puzzle_id = key[len(prefix):]
            date = ymd_to_date(puzzle_id[-8:])
        except (ValueError, json.JSONDecodeError):
            continue
        if value.get("playTime") is not None and value.get("completed"):
            out[date] = {"play_ms": value["playTime"], "puzzle_id": puzzle_id}
    return out


def load_existing(output: str) -> dict[str, dict]:
    rows = {}
    try:
        with open(output, newline="") as f:
            for row in csv.DictReader(f):
                rows[row["date"]] = row
    except FileNotFoundError:
        pass
    return rows


def write_stats_snapshot(streak: dict, path: str) -> dict:
    avg_ms  = streak.get("averagePlayTime")
    fast_ms = streak.get("fastestPlayTime")
    snap = {
        "snapshot_date":   datetime.today().strftime("%Y-%m-%d"),
        "games_played":    streak.get("gamesPlayed"),
        "games_won":       streak.get("gamesWon"),
        "win_percentage":  streak.get("winPercentage"),
        "average_seconds": round(avg_ms / 1000) if avg_ms else None,
        "average_time":    format_time(round(avg_ms / 1000)) if avg_ms else "",
        "fastest_seconds": round(fast_ms / 1000) if fast_ms else None,
        "fastest_time":    format_time(round(fast_ms / 1000)) if fast_ms else "",
        "crux_streak_current": streak.get("currentStreak"),
        "crux_streak_max":     streak.get("maxStreak"),
    }
    with open(path, "w") as f:
        json.dump(snap, f, indent=2)
    return snap


def main():
    parser = argparse.ArgumentParser(
        description="Track NRC Crux solved-status + stats (server-side, CI-safe).",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__,
    )
    parser.add_argument("--output", default=os.path.join(DATA_DIR, "crux_scores.csv"))
    parser.add_argument("--stats-output", default=os.path.join(DATA_DIR, "crux_stats.json"))
    parser.add_argument("--player-id", default=os.getenv("NRC_PLAYER_ID"))
    parser.add_argument("--user-id",   default=os.getenv("NRC_USER_ID"))
    parser.add_argument("--start", default=None,
                        help="Earliest date to record (default: start of the "
                             "server's authoritative window).")
    parser.add_argument("--dump", default=None,
                        help="Optional browser storage export for solve times.")
    args = parser.parse_args()

    if not args.player_id or not args.user_id:
        print("Error: set NRC_PLAYER_ID and NRC_USER_ID in .env (or pass flags).")
        sys.exit(1)

    session = requests.Session()
    crux = fetch_overview(session, args.user_id, args.player_id)
    streak = crux.get("streak", {}) or {}
    games = streak.get("games", []) or []

    # Dead-token guard. A live account always reports gamesPlayed (an int) in
    # its streak. When the NRC tokens rotate, the overview still yields a generic
    # Crux entry — but with an empty streak — which would silently overwrite real
    # solved flags with all-False and null out the stats. Bail BEFORE writing any
    # files so the last-good data is preserved, and exit non-zero so CI can email.
    if streak.get("gamesPlayed") is None:
        print("Error: NRC overview returned no streak data — the NRC_PLAYER_ID / "
              "NRC_USER_ID tokens have most likely rotated. Refresh them in .env "
              "(or repo Settings -> Secrets) from a fresh browser session.",
              file=sys.stderr)
        sys.exit(1)

    # Authoritative finished/not-finished signal.
    completed = {g["puzzleDate"] for g in games if g.get("completed")}
    puzzle_ids = {g["puzzleDate"]: g["puzzleId"] for g in games if g.get("puzzleId")}
    today = crux.get("puzzleDate")
    if today:
        puzzle_ids.setdefault(today, crux.get("puzzleId", ""))
        if crux.get("status") == "solved":
            completed.add(today)

    window_dates = sorted(g["puzzleDate"] for g in games) + ([today] if today else [])
    if not window_dates:
        print("No Crux history found in overview.")
        sys.exit(0)
    start = args.start or min(window_dates)
    end   = today or max(window_dates)

    dump_times = parse_dump_times(args.dump, args.player_id) if args.dump else {}

    existing = load_existing(args.output)
    print(f"Crux window {start} -> {end}  "
          f"({len(completed)} solved in range; {len(existing)} rows on file).")

    # Walk every date in the authoritative window; refresh solved status,
    # fetch metadata once per new date, optionally enrich with times.
    rows = dict(existing)
    d  = datetime.strptime(start, "%Y-%m-%d")
    dt = datetime.strptime(end,   "%Y-%m-%d")
    new_meta = 0
    while d <= dt:
        date = d.strftime("%Y-%m-%d")
        d += timedelta(days=1)

        row = rows.get(date, {})
        # metadata: fetch only if we don't have it yet
        if not row.get("constructor") and not row.get("puzzle_id"):
            meta = fetch_metadata(session, args.player_id, date)
            time.sleep(RATE_DELAY)
            if meta is None:
                continue  # no puzzle that day
            new_meta += 1
            row.update({
                "puzzle_id":   meta["puzzle_id"] or puzzle_ids.get(date, ""),
                "constructor": meta["constructor"],
                "width":       meta["width"],
                "height":      meta["height"],
            })
        row.setdefault("puzzle_id", puzzle_ids.get(date, ""))
        row["date"] = date
        row["puzzle_type"] = "crux"
        row["solved"] = date in completed

        # optional time enrichment from a storage dump
        if date in dump_times and not row.get("seconds"):
            play_ms = dump_times[date]["play_ms"]
            row["seconds"] = round(play_ms / 1000)
            row["time"]    = format_time(row["seconds"])
            gavg = fetch_global_avg(session, args.player_id, args.user_id,
                                    dump_times[date]["puzzle_id"], date, play_ms)
            time.sleep(RATE_DELAY)
            if gavg != "":
                row["global_avg_seconds"] = gavg
                row["global_avg_time"]    = format_time(gavg)

        rows[date] = row
        sys.stdout.write(f"\r  {date}  solved={row['solved']}   ")
        sys.stdout.flush()

    # Write everything back, sorted by date.
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for date in sorted(rows):
            writer.writerow({k: rows[date].get(k, "") for k in FIELDNAMES})

    solved_n = sum(1 for r in rows.values() if str(r.get("solved")) == "True")
    print(f"\n\nDone — {len(rows)} dates in {args.output} "
          f"({solved_n} solved, {new_meta} new metadata fetches).")

    snap = write_stats_snapshot(streak, args.stats_output)
    print(f"\n--- Crux stats (saved to {args.stats_output}) ---")
    print(f"  Played   : {snap['games_played']} (won {snap['games_won']}, "
          f"{snap['win_percentage']}%)")
    print(f"  Average  : {snap['average_time']}   Fastest: {snap['fastest_time']}")
    print(f"  Streak   : {snap['crux_streak_current']} (max {snap['crux_streak_max']})")


if __name__ == "__main__":
    main()
