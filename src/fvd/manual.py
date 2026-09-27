"""Record files downloaded by hand into raw/manual/.

obr.uk refuses scripted requests, and a few files were never archived by the
Wayback Machine. Those were downloaded in a browser from the link on the OBR
landing page and saved under raw/manual/ with the name the server gave them.
To reproduce, download each link below in a browser into raw/manual/ and run
this module; the SHA-256 in inventory/sources.csv shows whether the file is
the same one used here.
"""

from __future__ import annotations

from .http import record_manual
from .paths import ROOT

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


def main() -> None:
    for name, url in MANUAL.items():
        path = MANUAL_DIR / name
        if not path.exists():
            print(f"missing: {path.relative_to(ROOT)} (download {url} in a browser)")
            continue
        record_manual(path, url, note="EFO tables; no Wayback capture of this link")
        print(f"recorded: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
