#!/usr/bin/env python3
"""
fetch_tufe.py — build assets/rates.json for Kira Artis Takip

Pulls the monthly consumer price index from TCMB EVDS v3, computes the
12-month average change for each month, and writes assets/rates.json.

ENDPOINT NOTES (hard-won — see EVDS_PYTHON_Kilavuzu_TR.pdf)
    * The v3 web service lives at /igmevdsms-dis/, NOT /service/evds/.
      The old path now falls through to the web frontend and returns an
      HTML page with status 200, which looks like a JSON parse error.
    * Parameters go in the PATH after a slash, not as a ?query string.
    * The API key goes in an HTTP header, not the URL.

SERIES
    TP.TUKFIY2025.GENEL is the 2025-rebased CPI index. Do NOT append a
    formula suffix — "TP.TUKFIY2025.GENEL-3" gives year-on-year percent
    change, which is a different number from the one the law requires.

THE FORMULA (this IS the definition in TBK m.344)
    12-month average change =
      (mean(index, last 12 months) / mean(index, previous 12 months) - 1) * 100

TIMING
    A lease renewing in month M uses the figure announced in M, computed
    from data through M-1. RENEWAL_OFFSET_MONTHS encodes that.

USAGE
    python fetch_tufe.py --check    # verify series + endpoint, print index
    python fetch_tufe.py            # compute, confirm interactively, write
    python fetch_tufe.py --yes      # non-interactive (CI); validates first
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

try:
    import pandas as pd
    import requests
except ImportError:
    sys.exit("Missing dependencies:  pip install requests pandas")

# ---------------------------------------------------------------------------
SERIES_CODE = "TP.TUKFIY2025.GENEL"     # raw index, no formula suffix
ENDPOINT = "https://evds3.tcmb.gov.tr/igmevdsms-dis"
START_YEAR = 2020
RENEWAL_OFFSET_MONTHS = 1
OUT_PATH = Path(__file__).parent / "rates.json"

# Sanity bounds for automated runs — tuned to catch a broken series or a
# parsing bug, not to second-guess reality.
#
# MAX_STEP was originally 5.0, which turned out to be wrong: during Turkey's
# 2022 inflation spike the 12-month average genuinely moved 5.0-5.4 points a
# month for half a year. Real volatility, not bad data. A series mix-up or
# rebasing would show up as a jump of tens of points, so 10.0 still catches
# the failures worth catching.
MIN_RATE, MAX_RATE, MAX_STEP = 0.0, 200.0, 10.0

# Only step-check recent months. Older figures were verified when first
# published, and a historically volatile stretch shouldn't block every
# future run. Range checks still apply to the whole series.
STEP_CHECK_MONTHS = 24

AYLAR = ["Ocak", "Subat", "Mart", "Nisan", "Mayis", "Haziran",
         "Temmuz", "Agustos", "Eylul", "Ekim", "Kasim", "Aralik"]
# ---------------------------------------------------------------------------


def api_key() -> str:
    key = os.environ.get("EVDS_API_KEY")
    if not key:
        sys.exit("EVDS_API_KEY is not set.\n"
                 "  Get one free at https://evds3.tcmb.gov.tr (Profilim -> API Key)\n"
                 '  cmd:         set EVDS_API_KEY=your_key\n'
                 '  PowerShell:  $env:EVDS_API_KEY="your_key"\n')
    return key


def fetch_index() -> pd.Series:
    """Monthly CPI index from EVDS v3, keyed 'YYYY-MM'."""
    start = f"01-01-{START_YEAR - 2}"
    end = date.today().strftime("%d-%m-%Y")

    # Params live in the path, not a query string. This is unusual and is
    # the single thing most likely to silently return the SPA shell.
    url = (f"{ENDPOINT}/series={SERIES_CODE}"
           f"&startDate={start}&endDate={end}&type=json&frequency=5")

    try:
        r = requests.get(url, headers={"key": api_key()}, timeout=30)
    except requests.RequestException as e:
        sys.exit(f"Could not reach EVDS: {e}")

    body = r.text.strip()
    if not body.startswith(("{", "[")):
        key = api_key()
        print(f"\nEVDS did not return JSON.  HTTP {r.status_code}")
        print(f"URL:  {url}")
        print(f"Key:  {key[:3]}...{key[-3:]} (length {len(key)})")
        print(f"\nFirst 300 chars:\n{'-'*60}\n{body[:300]}\n{'-'*60}")
        print("\nAn HTML page here means the endpoint moved again. Check the")
        print("EVDS Python Kilavuzu for the current web service path.\n")
        sys.exit(1)

    rows = r.json().get("items", [])
    if not rows:
        sys.exit(f"No data for {SERIES_CODE}. The series may have been rebased.")

    # Column name is the series code with dots swapped for underscores, but
    # find it positionally so a rename doesn't break us.
    ignore = {"Tarih", "UNIXTIME", "YEARWEEK"}
    cols = [c for c in rows[0] if c not in ignore]
    if not cols:
        sys.exit(f"Could not find a data column. First row: {rows[0]}")
    col = cols[0]

    recs = {}
    for row in rows:
        period, raw = row.get("Tarih"), row.get(col)
        if not period or raw in (None, "", "null"):
            continue
        y, m = str(period).split("-")[:2]
        recs[f"{int(y)}-{int(m):02d}"] = float(str(raw).replace(",", "."))

    if not recs:
        sys.exit(f"Parsed zero rows from column '{col}'.")

    return pd.Series(recs).sort_index()


def twelve_month_average_change(idx: pd.Series) -> pd.Series:
    trailing = idx.rolling(12).mean()
    return ((trailing / trailing.shift(12)) - 1) * 100


def build_rates(change: pd.Series) -> dict:
    out = {}
    for period, value in change.dropna().items():
        y, m = map(int, period.split("-"))
        m += RENEWAL_OFFSET_MONTHS
        y += (m - 1) // 12
        m = (m - 1) % 12 + 1
        if y >= START_YEAR:
            out[f"{y}-{m:02d}"] = round(float(value), 2)
    return dict(sorted(out.items()))


def validate(rates: dict) -> list:
    """Returns a list of problems. Empty list means the data looks sane."""
    problems = []
    items = sorted(rates.items())
    for key, v in items:
        if not (MIN_RATE <= v <= MAX_RATE):
            problems.append(f"{key}: {v} outside {MIN_RATE}-{MAX_RATE}")
    recent = items[-STEP_CHECK_MONTHS:]
    for (k1, v1), (k2, v2) in zip(recent, recent[1:]):
        if abs(v2 - v1) > MAX_STEP:
            problems.append(
                f"{k1}->{k2}: jumped {abs(v2-v1):.2f} points (max {MAX_STEP})")
    return problems


def write(rates: dict, verified: list):
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps({
            "updated": date.today().isoformat(),
            "source": f"TCMB EVDS v3 - {SERIES_CODE}",
            "note": "12-month average CPI change, keyed by lease renewal month",
            "verified": verified,
            "rates": rates,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"  Wrote {len(rates)} rates ({len(verified)} verified) -> {OUT_PATH}")


def print_table(rates: dict, n=14):
    print(f"\n  Most recent {n} renewal months:")
    print("  " + "-" * 32)
    for key in list(rates)[-n:]:
        y, m = map(int, key.split("-"))
        print(f"  {AYLAR[m-1]:<9} {y}   %{rates[key]:>6.2f}")
    print("  " + "-" * 32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify endpoint and series, write nothing")
    ap.add_argument("--yes", action="store_true",
                    help="non-interactive; validates and marks verified")
    args = ap.parse_args()

    idx = fetch_index()

    if args.check:
        print(f"\nSeries {SERIES_CODE} -> {len(idx)} monthly values")
        print(f"Range: {idx.index[0]} to {idx.index[-1]}\n")
        print("Last 6 raw index values:")
        for k, v in idx.tail(6).items():
            print(f"  {k}   {v:>12,.2f}")
        print("\nThese should be index LEVELS (large, rising), not percentages.\n")
        return

    rates = build_rates(twelve_month_average_change(idx))
    if not rates:
        sys.exit("No rates computed — not enough index history.")

    print_table(rates)

    problems = validate(rates)
    if problems:
        print("\n  VALIDATION FAILED:")
        for p in problems:
            print(f"    {p}")
        print("\n  Not writing. Investigate before shipping these numbers.\n")
        sys.exit(1)

    if args.yes:
        write(rates, sorted(rates.keys()))
        return

    print("\n  Cross-check the newest against a public source.")
    print("  Known good: Agustos 2026 = %31.90, Temmuz 2026 = %32.03\n")
    ok = input("  Look correct? Mark all verified? [y/N] ").strip().lower() == "y"
    write(rates, sorted(rates.keys()) if ok else [])
    if not ok:
        print("  Written as UNVERIFIED — the app will flag every result.\n")


if __name__ == "__main__":
    main()
