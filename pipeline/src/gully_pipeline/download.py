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


# ---------------------------------------------------------------- snapshots
# Cricsheet answers datacenter IPs (e.g. GitHub Actions runners) with a browser
# check, so CI can't fetch it directly. A snapshot is the same two files published
# from a normal machine as a GitHub Release tagged data-YYYY-MM-DD; Cricsheet's
# ODC-BY licence allows redistribution with attribution (in the release notes).
SNAPSHOT_PREFIX = "data-"
SNAPSHOT_FILES = {"all_json.zip": ZIP_MAGIC, "people.csv": REGISTER_HEADER}


def latest_snapshot(repo: str) -> dict:
    """Newest data-* release of ``repo`` (owner/name) via the public GitHub API."""
    r = httpx.get(f"https://api.github.com/repos/{repo}/releases", timeout=60,
                  headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    r.raise_for_status()
    snaps = [rel for rel in r.json() if rel["tag_name"].startswith(SNAPSHOT_PREFIX)]
    if not snaps:
        raise DownloadError(f"{repo} has no {SNAPSHOT_PREFIX}* release; run `gully-pipeline snapshot` first")
    return max(snaps, key=lambda rel: rel["tag_name"])


def download_snapshot(repo: str, raw_dir: Path = RAW_DIR) -> tuple[str, list[Path]]:
    """Fetch the newest snapshot's files into ``raw_dir``. Returns (tag, paths)."""
    rel = latest_snapshot(repo)
    assets = {a["name"]: a["browser_download_url"] for a in rel["assets"]}
    missing = set(SNAPSHOT_FILES) - set(assets)
    if missing:
        raise DownloadError(f"snapshot {rel['tag_name']} is missing {sorted(missing)}")
    paths = [_fetch(assets[name], raw_dir / name, magic) for name, magic in SNAPSHOT_FILES.items()]
    return rel["tag_name"], paths


def download_dataset(name: str, raw_dir: Path = RAW_DIR) -> Path:
    filename = DATASETS[name]
    return _fetch(f"{BASE}/downloads/{filename}", raw_dir / filename, ZIP_MAGIC)


def download_register(raw_dir: Path = RAW_DIR) -> Path:
    return _fetch(f"{BASE}/register/people.csv", raw_dir / "people.csv", REGISTER_HEADER)
