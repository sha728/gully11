"""Publish the downloaded Cricsheet files as a GitHub Release ("data snapshot").

CI can't download from cricsheet.org (its runners get a browser check), so the
integration workflow reads the newest data-YYYY-MM-DD release instead. Run this
from a normal machine after `gully-pipeline download --dataset all`.

Uses the GitHub CLI (`gh`), so whichever token/account gh uses for the repo applies.
"""

from __future__ import annotations

import subprocess
import tempfile
from datetime import date
from pathlib import Path

from .download import SNAPSHOT_FILES, SNAPSHOT_PREFIX
from .paths import RAW_DIR

NOTES = """Cricsheet data snapshot for CI ({day}).

Files are unmodified downloads from https://cricsheet.org/downloads/ and
https://cricsheet.org/register/: `all_json.zip` (every match, JSON) and `people.csv`
(the player register). Match data © Cricsheet, licensed under the Open Data Commons
Attribution License (https://cricsheet.org/licensing/).

Used by `.github/workflows/integration.yml` because cricsheet.org challenges requests
from CI servers. Refresh with `gully-pipeline download --dataset all` then
`gully-pipeline snapshot`.
"""


def publish(repo: str, raw_dir: Path = RAW_DIR, day: date | None = None) -> str:
    day = day or date.today()
    tag = f"{SNAPSHOT_PREFIX}{day.isoformat()}"
    files = []
    for name, magic in SNAPSHOT_FILES.items():
        p = raw_dir / name
        if not p.exists():
            raise SystemExit(f"{p} missing; run `gully-pipeline download --dataset all` first")
        with p.open("rb") as f:
            if not f.read(len(magic)).startswith(magic):
                raise SystemExit(f"{p} doesn't look like the real file; re-download it")
        files.append(str(p))
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(NOTES.format(day=day.isoformat()))
        notes = f.name
    try:
        subprocess.run(["gh", "release", "create", tag, *files, "--repo", repo,
                        "--title", f"Data snapshot {day.isoformat()}", "--notes-file", notes,
                        "--latest=false"], check=True)
    finally:
        Path(notes).unlink(missing_ok=True)
    return tag
