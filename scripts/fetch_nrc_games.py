#!/usr/bin/env python3
"""
NRC puzzles — daily finished/not-finished tracker (all games except Crux)
--------------------------------------------------------------------------
Crux (the crossword) has its own richer tracker with solve times and
metadata — see fetch_nrc.py. This script covers every OTHER game on NRC's
puzzle hub with the same binary "did I finish it" signal, in a single
write-free API call:

    https://api.42puzzles.com/hub/nrc/overview?userId=<NRC_USER_ID>

The overview's per-game `streak.games[]` list is a rolling window (everything
since the platform's last stats snapshot, not full history) — this script
merges it into whatever's already on file rather than overwriting, so dates
that later roll out of the window stay recorded.

Output: data/nrc_games.csv  (date, <game-slug>, ... -> True/False)

Games and slugs mirror NRC's own renderer names:
  vorto (Wordle-style), precies-vier (Connections-style), sudoku,
  cijferblok, koprol, aan-zet (chess), scrypto, in-het-midden, woordzoeker,
  briljant (Queens-style)

Usage:
    python scripts/fetch_nrc_games.py
    python scripts/fetch_nrc_games.py --output data/nrc_games.csv
"""

import argparse
import csv
import os
import sys

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

API_BASE     = "https://api.42puzzles.com"
OVERVIEW_URL = f"{API_BASE}/hub/nrc/overview"
HEADERS = {
    "Origin":  "https://www.nrc.nl",
    "Referer": "https://www.nrc.nl/",
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}

# NRC renderer -> our slug. "crossword" (Crux) is intentionally excluded —
# see fetch_nrc.py for the richer, dedicated Crux tracker.
RENDERER_SLUG = {
    "wordle":      "vorto",
    "connections": "precies-vier",
    "sudoku":      "sudoku",
    "cijferblok":  "cijferblok",
    "koprol":      "koprol",
    "chess":       "aan-zet",
    "scrypto":     "scrypto",
    "inHetMidden": "in-het-midden",
    "wordfind":    "woordzoeker",
    "queens":      "briljant",
}
GAMES      = sorted(RENDERER_SLUG.values())
FIELDNAMES = ["date"] + GAMES


def fetch_overview(user_id: str) -> list[dict]:
    resp = requests.get(OVERVIEW_URL, params={"userId": user_id},
                        headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json().get("puzzles", []) or []


def load_existing(path: str) -> dict[str, dict]:
    rows = {}
    try:
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                rows[r["date"]] = {g: r.get(g) == "True" for g in GAMES}
    except FileNotFoundError:
        pass
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user-id", default=os.getenv("NRC_USER_ID"))
    parser.add_argument("--output", default=os.path.join(DATA_DIR, "nrc_games.csv"))
    args = parser.parse_args()

    if not args.user_id:
        print("Error: set NRC_USER_ID in .env (or pass --user-id).")
        sys.exit(1)

    puzzles = fetch_overview(args.user_id)

    # Dead-token guard, same idea as fetch_nrc.py: a live account reports a
    # streak (even if empty of games) for every renderer we track. If NONE
    # of them do, the tokens have most likely rotated — bail before writing
    # anything so last-good data isn't silently overwritten with all-False.
    tracked = [p for p in puzzles if p.get("renderer") in RENDERER_SLUG]
    if not tracked or all(p.get("streak") is None for p in tracked):
        print("Error: NRC overview returned no streak data for any tracked "
              "game — the NRC_USER_ID token has most likely rotated. "
              "Refresh it in .env (or repo Settings -> Secrets) from a "
              "fresh browser session.", file=sys.stderr)
        sys.exit(1)

    rows = load_existing(args.output)
    for p in tracked:
        slug = RENDERER_SLUG[p["renderer"]]
        for g in (p.get("streak", {}) or {}).get("games", []) or []:
            if g.get("completed"):
                date = g["puzzleDate"]
                rows.setdefault(date, {g2: False for g2 in GAMES})[slug] = True
        if p.get("status") == "solved" and p.get("puzzleDate"):
            date = p["puzzleDate"]
            rows.setdefault(date, {g2: False for g2 in GAMES})[slug] = True

    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for date in sorted(rows):
            writer.writerow({"date": date, **{g: rows[date].get(g, False) for g in GAMES}})

    total = {g: sum(1 for r in rows.values() if r.get(g)) for g in GAMES}
    print(f"Done — {len(rows)} dates in {args.output}.")
    print("  finished totals: " + ", ".join(f"{g}={total[g]}" for g in GAMES))


if __name__ == "__main__":
    main()
