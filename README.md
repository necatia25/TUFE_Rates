# kira-takip-rates

Monthly TÜFE (Turkish CPI) 12-month average change, published as JSON for
the Kira Artış Takip app to fetch at runtime.

This repository is public **only** so that `raw.githubusercontent.com` can
serve `rates.json` without authentication. It contains no application code.

## What's here

| File | Purpose |
|---|---|
| `rates.json` | The published data. The app fetches this. |
| `fetch_tufe.py` | Pulls the CPI index from TCMB EVDS and computes the rates. |
| `.github/workflows/update-rates.yml` | Runs the script monthly and commits changes. |

## Setup (once)

1. Settings → Secrets and variables → Actions → New repository secret
   - Name: `EVDS_API_KEY`
   - Value: your key from evds3.tcmb.gov.tr (Profilim → API Key)
2. Actions tab → "Update TÜFE rates" → "Run workflow" to test immediately.

After that it runs by itself on the 4th of each month.

## How the rate is derived

The legal ceiling in Türk Borçlar Kanunu Madde 344 is the 12-month average
change in CPI:

    (mean(index, last 12 months) / mean(index, previous 12 months) - 1) × 100

A lease renewing in month M uses the figure announced in M, which is computed
from index data through M-1.

## Safety

`--yes` mode validates before writing: rates must fall within sane bounds, and
consecutive months can't jump more than 10 percentage points. If a check fails
the script exits non-zero, the workflow fails, and nothing is committed.

The 10-point threshold is deliberately loose — during Turkey's 2022 inflation
spike the 12-month average genuinely moved over 5 points a month. A broken
series or a rebasing would show up as a jump of tens of points.

## When EVDS changes

It has twice already: the endpoint moved from `evds2/service/evds/` to
`evds3/igmevdsms-dis/`, and the CPI series was rebased from `TP.FG.J0` to
`TP.TUKFIY2025.GENEL`. Both are constants at the top of `fetch_tufe.py`.

Run `python fetch_tufe.py --check` locally to see what the endpoint returns.
Meanwhile the app keeps serving the last good `rates.json`, so users are
unaffected while it's fixed.
