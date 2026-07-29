import pytest

from file_organizer.config import (
    Config,
    Options,
    RuleSpec,
    load_config,
    parse_size,
)
from file_organizer.errors import ConfigError
from file_organizer.models import ConflictStrategy, DateBasis


def test_parse_size_units():
    assert parse_size("1MB") == 1024**2
    assert parse_size("100MB") == 100 * 1024**2
    assert parse_size("500KB") == 500 * 1024
    assert parse_size("2GB") == 2 * 1024**3
    assert parse_size(4096) == 4096
    assert parse_size("2048") == 2048
    assert parse_size("1.5MB") == int(1.5 * 1024**2)


def test_parse_size_errors():
    with pytest.raises(ConfigError):
        parse_size("10ZB")
    with pytest.raises(ConfigError):
        parse_size(-5)
    with pytest.raises(ConfigError):
        parse_size(True)
    with pytest.raises(ConfigError):
        parse_size("not a size")


def test_load_sample_config(fixtures_dir):
    cfg = load_config(fixtures_dir / "sample-config.yaml")
    assert isinstance(cfg, Config)
    names = [r.name for r in cfg.rules]
    assert "images" in names
    assert cfg.options.conflict_strategy == ConflictStrategy.RENAME


def test_min_size_string_converted():
    cfg = Config.from_dict(
        {
            "rules": [
                {"name": "z", "extensions": ["zip"], "min_size": "1MB",
                 "destination": "{source}/Z"},
            ]
        }
    )
    assert cfg.rules[0].min_size == 1024**2


def test_duplicate_name_raises():
    with pytest.raises(ConfigError):
        Config.from_dict(
            {
                "rules": [
                    {"name": "dup", "extensions": ["a"], "destination": "d1"},
                    {"name": "dup", "extensions": ["b"], "destination": "d2"},
                ]
            }
        )


def test_bad_regex_raises(fixtures_dir):
    with pytest.raises(ConfigError):
        load_config(fixtures_dir / "bad-config.yaml")


def test_unknown_top_level_key():
    with pytest.raises(ConfigError):
        Config.from_dict({"bogus": 1, "rules": []})


def test_unknown_option_key():
    with pytest.raises(ConfigError):
        Config.from_dict({"options": {"nope": 1}, "rules": []})


def test_unknown_rule_key():
    with pytest.raises(ConfigError):
        Config.from_dict(
            {"rules": [{"name": "x", "destination": "d", "weird": 1}]}
        )


def test_empty_name_raises():
    with pytest.raises(ConfigError):
        Config.from_dict({"rules": [{"name": "  ", "destination": "d"}]})


def test_empty_destination_raises():
    with pytest.raises(ConfigError):
        Config.from_dict({"rules": [{"name": "x", "destination": ""}]})


def test_default_config():
    cfg = Config.default()
    assert any(r.name == "images" for r in cfg.rules)
    assert any(r.is_catch_all for r in cfg.rules)


def test_options_from_dict_enums():
    opts = Options.from_dict(
        {"conflict_strategy": "overwrite", "date_basis": "created"}
    )
    assert opts.conflict_strategy == ConflictStrategy.OVERWRITE
    assert opts.date_basis == DateBasis.CREATED


def test_options_invalid_enum():
    with pytest.raises(ConfigError):
        Options.from_dict({"conflict_strategy": "nope"})


def test_cli_override_merge():
    cfg = Config.default()
    merged = cfg.with_overrides(
        conflict_strategy=ConflictStrategy.SKIP, recursive=True
    )
    assert merged.options.conflict_strategy == ConflictStrategy.SKIP
    assert merged.options.recursive is True
    # None overrides are ignored
    merged2 = cfg.with_overrides(recursive=None)
    assert merged2.options.recursive == cfg.options.recursive


def test_size_range_parsing():
    cfg = Config.from_dict(
        {
            "rules": [
                {
                    "name": "mid",
                    "size_range": ["1KB", "1MB"],
                    "destination": "{source}/Mid",
                }
            ]
        }
    )
    assert cfg.rules[0].size_range == (1024, 1024**2)


def test_size_range_bad_shape():
    with pytest.raises(ConfigError):
        Config.from_dict(
            {"rules": [{"name": "x", "size_range": [1], "destination": "d"}]}
        )


def test_missing_config_file(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")


def test_config_root_not_mapping(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("- a\n- b\n")
    with pytest.raises(ConfigError):
        load_config(p)


def test_empty_config_file(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("")
    cfg = load_config(p)
    assert cfg.rules == []


def test_selector_count_and_catch_all():
    r = RuleSpec(name="x", destination="d")
    assert r.is_catch_all
    r2 = RuleSpec(name="y", destination="d", extensions=["a"], min_size=1)
    assert r2.selector_count == 2
