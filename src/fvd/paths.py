"""Repository paths. Artifact names follow section 11 of the plan and are fixed."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RAW = ROOT / "raw"
RAW_OBR = RAW / "obr"
RAW_CBO = RAW / "cbo"
RAW_DOCS = RAW / "documents"
RAW_WEB = RAW / "web"  # cached listing and landing pages

INVENTORY = ROOT / "inventory"
CROSSWALKS = ROOT / "crosswalks"
TABLES = ROOT / "tables"
STATS = ROOT / "stats"
TEXT = ROOT / "text"
CASES = ROOT / "cases"
NOTES = ROOT / "notes" / "extraction"

SOURCES_CSV = INVENTORY / "sources.csv"
