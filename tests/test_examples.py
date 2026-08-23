"""The shipped example configs must stay loadable.

They are what people copy from, so a schema change that invalidates one is a broken front door.
This test fails the moment an example drifts out of step with the validator.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from statement_reconciler.config import load_config

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((ROOT / "examples" / "configs").glob("*.yaml"))


def test_examples_are_present():
    """A glob that silently matches nothing would make every test below vacuously pass."""
    assert EXAMPLES, "no example configs found under examples/configs/"


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_example_config_loads(path):
    config = load_config(path)
    assert config.sources


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_example_pairs_records_somehow(path):
    """Exactly one pairing mode, and its fields readable from both sides -- load_config enforces
    this, so the assertion is really that every example exercises one path or the other."""
    for source in load_config(path).sources:
        assert bool(source.match_on) != bool(source.match_key)
        if source.match_on:
            assert source.compare_fields


def test_the_top_level_example_loads():
    assert load_config(ROOT / "config.example.yaml").sources
