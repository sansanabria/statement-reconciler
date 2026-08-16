from __future__ import annotations

import copy
from datetime import date

import pytest
import yaml

from statement_reconciler.config import ConfigError, MailRule, load_config, parse_config

pytestmark = pytest.mark.unit


def test_parses_a_valid_config(config_dict):
    config = parse_config(config_dict)
    assert [s.name for s in config.sources] == ["EXAMPLE_SOURCE"]
    assert config.sources[0].match_key == ("date", "description", "amount", "quantity")


def test_example_file_is_valid():
    """The shipped example must actually load -- it is the template everyone copies."""
    config = load_config("config.example.yaml")
    assert config.sources


def test_folder_template_renders(config_dict):
    config = parse_config(config_dict)
    folder = config.folder_for("EXAMPLE_SOURCE", date(2026, 3, 2))
    assert folder.name == "EXAMPLE_SOURCE 2026.03.02"
    assert folder.parent.name == "EXAMPLE_SOURCE"


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda c: c.pop("output_root"), "output_root"),
        (lambda c: c.pop("folder_template"), "folder_template"),
        (lambda c: c.update(sources=[]), "at least one source"),
        (lambda c: c.update(nonsense=1), "unknown key"),
        (lambda c: c["sources"][0].pop("match_key"), "match_key"),
        (lambda c: c["sources"][0]["records"].pop("amount"), "amount"),
        (lambda c: c["sources"][0]["document"]["columns"].pop("quantity"), "quantity"),
        (lambda c: c["sources"][0]["records"].update(nope=["X"]), "not a known field"),
        (lambda c: c["sources"][0].update(match={}), "matches nothing"),
        (lambda c: c["sources"][0]["document"]["columns"].update(date="left"), "expected a number"),
        (lambda c: c.update(folder_template="{whoops}"), "could not be rendered"),
        (lambda c: c.update(min_attachment_bytes=-1), "non-negative"),
    ],
)
def test_invalid_config_names_the_offending_key(config_dict, mutate, expected):
    broken = copy.deepcopy(config_dict)
    mutate(broken)
    with pytest.raises(ConfigError, match=expected):
        parse_config(broken)


def test_duplicate_source_names_rejected(config_dict):
    config_dict["sources"].append(copy.deepcopy(config_dict["sources"][0]))
    with pytest.raises(ConfigError, match="duplicate source name"):
        parse_config(config_dict)


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "absent.yaml")


def test_invalid_yaml(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("sources: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(path)


def test_load_from_disk(tmp_path, config_dict):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config_dict), encoding="utf-8")
    assert load_config(path).sources[0].name == "EXAMPLE_SOURCE"


def test_source_lookup_is_case_insensitive(config):
    assert config.source("example_source").name == "EXAMPLE_SOURCE"
    with pytest.raises(ConfigError, match="No source named"):
        config.source("absent")


class TestMailRule:
    def test_subject_needs_every_fragment(self):
        rule = MailRule(subject_all=("Daily", "Statement"))
        assert rule.matches("Your daily statement is ready")
        assert not rule.matches("Your daily summary is ready")

    def test_attachment_route_catches_forwards(self):
        rule = MailRule(subject_all=("Daily",), attachment_contains=("daily_statement",))
        assert rule.matches("FW: something else", ("Daily_Statement_01.pdf",))

    def test_no_match(self):
        assert not MailRule(attachment_contains=("x",)).matches("subject", ("y.pdf",))


class TestPickColumn:
    def test_first_alias_present_wins(self, source):
        assert source.records.pick_column(("Value Date", "Details"), "date") == "Value Date"

    def test_matching_ignores_case_and_padding(self, source):
        assert source.records.pick_column(("  date  ",), "date") == "  date  "

    def test_error_lists_tried_and_actual(self, source):
        with pytest.raises(ConfigError) as excinfo:
            source.records.pick_column(("Booking Day",), "date")
        message = str(excinfo.value)
        assert "Value Date" in message and "Booking Day" in message
