"""Download Cricsheet JSON archives and the people register.

Cricsheet data is licensed under ODC-BY: credit Cricsheet wherever it is shown.
"""

from pathlib import Path

import httpx

from .paths import RAW_DIR

BASE = "https://cricsheet.org"

# Dataset name -> archive filename on cricsheet.org/downloads/
DATASETS = {
    "all": "all_json.zip",
    "tests": "tests_json.zip",
    "odis": "odis_json.zip",
    "t20s": "t20s_json.zip",
    "ipl": "ipl_json.zip",
}

USER_AGENT = "gully11-pipeline/0.1"


def _fetch(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=120,
                      headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    tmp.replace(dest)
    return dest


def download_dataset(name: str, raw_dir: Path = RAW_DIR) -> Path:
    filename = DATASETS[name]
    return _fetch(f"{BASE}/downloads/{filename}", raw_dir / filename)


def download_register(raw_dir: Path = RAW_DIR) -> Path:
    return _fetch(f"{BASE}/register/people.csv", raw_dir / "people.csv")
