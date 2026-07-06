# nrc-puzzel-tracker

Track your personal [NRC Crux](https://www.nrc.nl/puzzels/crux/) (crossword)
solve history automatically via a scheduled GitHub Action. As far as I could
find, there's no existing open-source tool for this — most NYT-crossword
scrapers exist, but nothing for NRC's puzzle platform.

*Nederlands hieronder.*

## What you get

- `data/crux_scores.csv` — one row per date: puzzle id, constructor, size,
  solved/not, and (optionally, see below) your solve time plus that
  puzzle's global average.
- `data/crux_stats.json` — a snapshot of your aggregate stats: games
  played/won, win %, average/fastest time, current and max streak.

## Setup

1. **Fork this repo.**
2. **Get your NRC tokens** (`NRC_PLAYER_ID` and `NRC_USER_ID` — stable
   tokens, unlike a login cookie these don't expire):
   - Open [nrc.nl/puzzels/crux](https://www.nrc.nl/puzzels/crux/) while
     logged in and open a puzzle.
   - DevTools (F12) → Network tab → look at requests to
     `api.42puzzles.com` — the query string / request body has both.
   - Or: Application/Storage → Local Storage → the `oneplayer-userid` key
     holds the user id.
3. **Add them as repo secrets:** Settings → Secrets and variables → Actions
   → add `NRC_PLAYER_ID` and `NRC_USER_ID`.
4. **Enable Actions** on your fork.

The `NRC Crux` workflow runs 6×/day and commits any new solves to `data/`.

### Running locally

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in NRC_PLAYER_ID / NRC_USER_ID

python scripts/fetch_nrc.py
```

## Why solve times are only "sometimes" available

NRC's server only stores an aggregate + a per-date solved/not-finished flag
— your actual solve *time* lives in your browser's local storage, and only
for roughly the last week. `fetch_nrc.py` always records the solved flag
(that's what the scheduled Action does). If you also want times:

1. Open a Crux page, DevTools → Console, paste in
   [`tools/crux_export_snippet.js`](tools/crux_export_snippet.js), press
   Enter — it downloads `crux_storage_dump.json`.
2. Run `python scripts/fetch_nrc.py --dump ~/Downloads/crux_storage_dump.json`
   to backfill times (and that puzzle's global average) for whatever dates
   the export still holds.

Re-export roughly weekly if you want to catch every day before it rolls off
local storage — there's no way to automate this part in CI since it needs
your actual browser storage.

## Disclaimer

This project uses an undocumented REST API (`api.42puzzles.com`, the
platform NRC's puzzles run on) and is not affiliated with or endorsed by
NRC Media or 42puzzles. This endpoint can change or break without notice.
`fetch_nrc.py` already guards against the most likely failure mode — if the
tokens rotate, the overview call comes back with no streak data, and the
script exits loudly instead of silently overwriting your history with
all-`False`. Use at your own risk, and don't hammer their servers.

## License

MIT — see [LICENSE](LICENSE).

---

## Nederlands

Volgt automatisch je persoonlijke oplostijden voor de
[NRC Crux](https://www.nrc.nl/puzzels/crux/) via een geplande GitHub
Action. Voor zover ik kon vinden bestaat hier nog geen open-source tool
voor.

### Wat je krijgt

- `data/crux_scores.csv` — één rij per datum: puzzel-id, maker, formaat,
  opgelost of niet, en (optioneel) je oplostijd plus het gemiddelde van
  die puzzel.
- `data/crux_stats.json` — een snapshot van je totaalstatistieken: aantal
  gespeeld/gewonnen, winpercentage, gemiddelde/snelste tijd, huidige en
  langste reeks.

### Installatie

1. **Fork deze repo.**
2. **Haal je NRC-tokens op** (`NRC_PLAYER_ID` en `NRC_USER_ID` — dit zijn
   stabiele tokens die niet verlopen zoals een login-cookie):
   - Open [nrc.nl/puzzels/crux](https://www.nrc.nl/puzzels/crux/), ingelogd,
     en open een puzzel.
   - DevTools (F12) → Network-tab → bekijk requests naar
     `api.42puzzles.com` — beide staan in de query string / request body.
   - Of: Application/Storage → Local Storage → de sleutel
     `oneplayer-userid` bevat de user id.
3. **Zet ze als repo secrets:** Settings → Secrets and variables → Actions
   → voeg `NRC_PLAYER_ID` en `NRC_USER_ID` toe.
4. **Zet Actions aan** op je fork.

De workflow `NRC Crux` draait 6×/dag en committeert nieuwe oplossingen naar
`data/`.

### Oplostijden

De server van NRC bewaart alleen een totaalcijfer en of je een puzzel wel
of niet hebt opgelost — je daadwerkelijke oplostijd staat alleen lokaal in
je browser (ongeveer de laatste week). Zie de Engelstalige uitleg hierboven
voor de exportstap met `tools/crux_export_snippet.js`.
