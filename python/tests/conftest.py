"""Every test runs against a minimal project in a temporary folder: the
Gregorian calendar, and none of a story's files."""

import atexit
import json
import shutil
import tempfile
from pathlib import Path

from galaxy import project

_ROOT = Path(tempfile.mkdtemp(prefix="galaxy-test-"))
atexit.register(shutil.rmtree, _ROOT, ignore_errors=True)
(_ROOT / "calendar.json").write_text(json.dumps({
    "eras": {"BC": {"zero": 0, "direction": -1}, "AD": {"zero": 0, "direction": 1}},
    "written": [{"era": "AD", "from": 1}, {"era": "BC"}],
    "epoch": "AD 2000",
}), encoding="utf-8")
(_ROOT / "project.toml").write_text("\n".join(f'{key} = "{key}.json"' for key in (
    "catalogue", "nations", "travel", "medium", "constellations", "procedural", "calendar"))
    + '\ndensity = "density.svg"\n', encoding="utf-8")
project.use(_ROOT / "project.toml")
