"""Optional live differential tests against a Stata binary.

Requires ``DO2SCREEN_STATA_BIN`` to point at a Stata binary (for example
``/Applications/Stata/StataMP.app/Contents/MacOS/stata-mp`` or ``stata`` on
PATH). Without it these tests skip with a clear reason; every other test in the
suite still runs.

The optional runner is tracked as plan verification row V12. It remains
non-blocking: without a Stata executable these tests skip, and this repository
does not ship the do2screen (Stata) ``variables()`` driver that would export
``r(lines)``. A Stata-capable validation environment may replace the placeholder
driver and run the corpus comparison separately (AGENTS.md section 5.1).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

STATA_BIN = os.environ.get("DO2SCREEN_STATA_BIN")

needs_stata = pytest.mark.skipif(
    STATA_BIN is None or not shutil.which(STATA_BIN),
    reason="DO2SCREEN_STATA_BIN not set: live Stata differential is opt-in",
)

GOLDEN_DIR = Path(__file__).parent.parent / "fixtures" / "stata_golden"

CASES = [
    ("golden_income.do", "income"),
    ("golden_income.do", "wages"),
    ("golden_rename_label.do", "hhsize"),
]


def _driver_for(fixture_abs: str, variable: str) -> str:
    """Build the current placeholder driver for one fixture.

    The package keeps this hook opt-in because the reference driver belongs to
    do2screen (Stata), not to do2screen-py.
    """
    # Built with plain string formatting (no nested f-strings) so the module is
    # a valid SyntaxError-free module on Python 3.10/3.11 as well as 3.12+.
    return (
        "version 13\n"
        f'* differential driver for {variable}\n'
        f'do "{fixture_abs}"\n'
        '* Optional reference driver unavailable in do2screen-py.\n'
        '* Run the corpus comparison in a Stata-capable validation environment.\n'
    )


def _line_numbers_from(raw: str) -> list[int]:
    parts = raw.replace(",", " ").split()
    return [int(p) for p in parts if p.strip().lstrip("-").isdigit()]


@needs_stata
@pytest.mark.xfail(
    reason="optional do2screen (Stata) reference driver is external (plan V12)",
    strict=False,
)
def test_live_differential(tmp_path):
    for fixture, variable in CASES:
        source = GOLDEN_DIR / fixture
        content = source.read_text(encoding="utf-8")
        from tests.conftest import trace_text

        expected, _ = trace_text(tmp_path, content, variable)
        expected_lines = sorted(r.start_line for r in expected.ranges)

        with tempfile.TemporaryDirectory() as tmp:
            out_file = Path(tmp) / "out.txt"
            driver = tmp_path / f"driver_{variable}.do"
            driver.write_text(
                _driver_for(str(source.resolve()), variable), encoding="utf-8"
            )
            result = subprocess.run(
                [STATA_BIN, "-b", "-e", str(driver)],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if out_file.exists():
                actual_lines = _line_numbers_from(
                    out_file.read_text(encoding="utf-8")
                )
            else:
                actual_lines = []
                pytest.fail(
                    f"Stata driver produced no r(lines) output: {result.stderr}"
                )

        assert actual_lines == expected_lines, (
            f"{fixture} {variable}: Stata lines {actual_lines} "
            f"!= python lines {expected_lines}"
        )
