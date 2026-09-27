"""Files downloaded by hand into raw/manual/.

obr.uk refuses scripted requests. Files were downloaded in a browser from the
link on the OBR's own pages and saved under raw/manual/ with the name the
server gave them, for two purposes:

- MANUAL: files the Wayback Machine never archived. They are recorded in
  inventory/sources.csv (via = manual) and used by the pipeline.
- CHECKS: files the pipeline takes from the archive. The browser copy is
  compared byte for byte with the archive copy (inventory/manual_checks.csv)
  and is not used otherwise.

To reproduce, download each link below in a browser into raw/manual/ and run
this module.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from .http import load_sources, record_manual, sha256_file
from .paths import INVENTORY, ROOT
from .schemas import check_columns, write_schema

MANUAL_DIR = ROOT / "raw" / "manual"

# file name as saved -> the link it was downloaded from (listed on the landing page)
MANUAL = {
    "efo_charts_tables_march2011.xls":
        "https://obr.uk/download/march-2011-economic-and-fiscal-outlook-charts-and-tables/",
    "December_2014_Charts_and_tables-web516.xls":
        "https://obr.uk/download/economic-and-fiscal-outlook-charts-and-tables-december-2014/",
    "Fiscal_charts_and_tables_October_2018.xlsx":
        "https://obr.uk/download/october-2018-economic-and-fiscal-outlook-charts-and-tables-fiscal/",
}

# file name as saved -> (link, raw file used in the pipeline)
CHECKS = {
    "Historical_official_forecasts_database_Spring_2026.xlsx":
        ("https://obr.uk/download/historical-official-forecasts-database-march-2025/",
         "raw/obr/Historical_official_forecasts_database_Spring_2026.xlsx"),
    "Fiscal_forecast_revisions_database_March_2026.xlsx":
        ("https://obr.uk/download/forecast-revisions-database-march-2025/",
         "raw/obr/Fiscal_forecast_revisions_database_March_2026.xlsx"),
    "Policy_measures_database_March_2026.xlsx":
        ("https://obr.uk/download/policy-measures-database-march-2025/",
         "raw/obr/Policy_measures_database_March_2026.xlsx"),
}


def record() -> None:
    for name, url in MANUAL.items():
        path = MANUAL_DIR / name
        if not path.exists():
            print(f"missing: {path.relative_to(ROOT)} (download {url} in a browser)")
            continue
        record_manual(path, url, note="EFO tables; no Wayback capture of this link")
        print(f"recorded: {path.relative_to(ROOT)}")


def compare() -> pd.DataFrame:
    sources = load_sources()
    rows = []
    for name, (url, used) in CHECKS.items():
        path = MANUAL_DIR / name
        if not path.exists():
            print(f"missing: {path.relative_to(ROOT)} (download {url} in a browser)")
            continue
        saved = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        mine, theirs = sha256_file(path), sources[used]["sha256"]
        rows.append({"manual_file": path.relative_to(ROOT).as_posix(), "url": url,
                     "compared_with": used, "downloaded_at": saved.isoformat(timespec="seconds"),
                     "sha256_manual": mine, "sha256_used": theirs, "identical": mine == theirs})
    df = pd.DataFrame(rows)
    check_columns("inventory/manual_checks", df)
    df.to_csv(INVENTORY / "manual_checks.csv", index=False)
    write_schema("inventory/manual_checks", ROOT)
    return df


def main() -> None:
    record()
    df = compare()
    if len(df):
        print(df[["manual_file", "identical"]].to_string(index=False))


if __name__ == "__main__":
    main()
