from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_auction_salvage_import_needs_no_settings_or_site_packages() -> None:
    service_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            (
                "import sys; import app.auction_salvage_import; "
                "assert 'app.settings' not in sys.modules; "
                "assert 'dotenv' not in sys.modules"
            ),
        ],
        cwd=service_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
