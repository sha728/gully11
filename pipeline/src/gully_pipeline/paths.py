from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PIPELINE_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PARQUET_DIR = DATA_DIR / "parquet"
