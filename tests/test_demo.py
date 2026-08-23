"""The runnable demo must keep working, and keep showing what it promises.

It is the first thing a newcomer runs, so a demo that errors or quietly reconciles cleanly
would be worse than having none at all.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from statement_reconciler.check import check_folder
from statement_reconciler.config import load_config

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent
BUILD_DEMO = ROOT / "examples" / "demo" / "build_demo.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_demo", BUILD_DEMO)
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_demo"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    pytest.importorskip("reportlab", reason="the demo draws a PDF with reportlab")
    root = tmp_path_factory.mktemp("demo") / "demo"
    builder = _load_builder()
    assert builder.main(["--out", str(root)]) == 0
    return root, builder


def test_it_writes_a_config_and_both_documents(demo):
    root, builder = demo
    folder = root / builder.SOURCE / f"{builder.SOURCE} 2026.03.02"
    assert (root / "config.yaml").is_file()
    assert list(folder.glob("*.pdf")) and list(folder.glob("*.xlsx"))


def test_the_generated_config_is_valid(demo):
    root, _ = demo
    assert load_config(root / "config.yaml").sources[0].match_on == "reference"


def test_refusing_to_overwrite_without_force(demo):
    root, builder = demo
    with pytest.raises(SystemExit):
        builder.main(["--out", str(root)])


@pytest.fixture(scope="module")
def demo_result(demo):
    root, builder = demo
    config = load_config(root / "config.yaml")
    folder = root / builder.SOURCE / f"{builder.SOURCE} 2026.03.02"
    result, _ = check_folder(folder, config)
    return result


class TestWhatTheDemoShows:

    def test_it_does_not_reconcile_cleanly(self, demo_result):
        """A demo that comes out green teaches nothing about what the tool is for."""
        assert not demo_result.reconciled

    def test_the_drawn_header_row_is_not_read_as_a_record(self, demo_result):
        """The demo PDF draws a header line; if it leaked through, every layout would too."""
        assert demo_result.unread_lines == ()

    def test_one_record_differs_on_amount(self, demo_result):
        assert len(demo_result.differing) == 1
        pair = demo_result.differing[0]
        assert pair.identifier == "INV-4472"
        assert [d.field for d in pair.differences] == ["amount"]

    def test_one_billed_but_not_booked_and_one_booked_but_not_billed(self, demo_result):
        references = sorted(r.values["reference"] for r in demo_result.unmatched)
        assert references == ["INV-4474", "INV-4480"]
