"""Download Cricsheet JSON archives and the people register.

Cricsheet data is licensed under ODC-BY: credit Cricsheet wherever it is shown.
"""

from __future__ import annotations

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

# Identify the client and where it comes from, as polite scrapers should.
USER_AGENT = "gully11-pipeline/0.1 (+https://github.com/sha728/gully11)"

ZIP_MAGIC = b"PK\x03\x04"
REGISTER_HEADER = b"identifier,"


class DownloadError(RuntimeError):
    """The server answered, but not with the file we asked for."""


def _check(head: bytes, expect: bytes, url: str, r: httpx.Response, size: int) -> None:
    if head.startswith(expect):
        return
    preview = head[:300].decode("utf-8", "replace").replace("\n", " ")
    raise DownloadError(
        f"{url} did not return the expected file (HTTP {r.status_code}, "
        f"content-type {r.headers.get('content-type', '?')}, {size:,} bytes). "
        f"Starts with: {preview!r}")


def _fetch(url: str, dest: Path, expect: bytes) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    head = b""
    size = 0
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120,
                          headers={"User-Agent": USER_AGENT}) as r:
            r.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    if len(head) < 512:
                        head += chunk[: 512 - len(head)]
                    size += len(chunk)
                    f.write(chunk)
        _check(head, expect, url, r, size)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(dest)
    return dest


def download_dataset(name: str, raw_dir: Path = RAW_DIR) -> Path:
    filename = DATASETS[name]
    return _fetch(f"{BASE}/downloads/{filename}", raw_dir / filename, ZIP_MAGIC)


def download_register(raw_dir: Path = RAW_DIR) -> Path:
    return _fetch(f"{BASE}/register/people.csv", raw_dir / "people.csv", REGISTER_HEADER)
