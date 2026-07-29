"""Configuration loading, parsing and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from file_organizer.errors import ConfigError
from file_organizer.models import ConflictStrategy, DateBasis

SIZE_UNITS = {
    "B": 1,
    "KB": 1024,
    "MB": 1024**2,
    "GB": 1024**3,
    "TB": 1024**4,
}

_SIZE_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([A-Za-z]+)?\s*$")


def parse_size(value: object) -> int:
    """Parse a human-readable size like ``"1MB"`` / ``"500KB"`` or a raw int.

    Accepts ints (interpreted as bytes) and strings with an optional unit.
    """
    if isinstance(value, bool):  # bool is an int subclass; reject explicitly
        raise ConfigError(f"Invalid size value: {value!r}")
    if isinstance(value, int):
        if value < 0:
            raise ConfigError(f"Size cannot be negative: {value!r}")
        return value
    if isinstance(value, float):
        return int(value)
    if not isinstance(value, str):
        raise ConfigError(f"Invalid size value: {value!r}")
    m = _SIZE_RE.match(value)
    if not m:
        raise ConfigError(f"Cannot parse size: {value!r}")
    number, unit = m.group(1), m.group(2)
    if unit is None:
        return int(float(number))
    unit = unit.upper()
    if unit not in SIZE_UNITS:
        raise ConfigError(f"Unknown size unit {unit!r} in {value!r}")
    return int(float(number) * SIZE_UNITS[unit])


@dataclass
class Options:
    dry_run: bool = False
    watch: bool = False
    undo_log: Path = field(default_factory=lambda: Path(".file-organizer-undo.jsonl"))
    conflict_strategy: ConflictStrategy = ConflictStrategy.RENAME
    follow_symlinks: bool = False
    date_basis: DateBasis = DateBasis.MODIFIED
    recursive: bool = False
    verify_hash: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> "Options":
        d = dict(d or {})
        known = {f.name for f in cls.__dataclass_fields__.values()}
        unknown = set(d) - known
        if unknown:
            raise ConfigError(
                f"Unknown option keys: {', '.join(sorted(unknown))}"
            )
        opts = cls()
        if "dry_run" in d:
            opts.dry_run = bool(d["dry_run"])
        if "watch" in d:
            opts.watch = bool(d["watch"])
        if "undo_log" in d:
            opts.undo_log = Path(d["undo_log"])
        if "conflict_strategy" in d:
            opts.conflict_strategy = _parse_enum(
                ConflictStrategy, d["conflict_strategy"], "conflict_strategy"
            )
        if "follow_symlinks" in d:
            opts.follow_symlinks = bool(d["follow_symlinks"])
        if "date_basis" in d:
            opts.date_basis = _parse_enum(DateBasis, d["date_basis"], "date_basis")
        if "recursive" in d:
            opts.recursive = bool(d["recursive"])
        if "verify_hash" in d:
            opts.verify_hash = bool(d["verify_hash"])
        return opts


def _parse_enum(enum_cls, value, name):
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(str(value).lower())
    except ValueError as exc:
        valid = ", ".join(e.value for e in enum_cls)
        raise ConfigError(
            f"Invalid {name}: {value!r} (expected one of {valid})"
        ) from exc


@dataclass
class RuleSpec:
    name: str
    destination: str
    extensions: list[str] | None = None
    size_range: tuple[int | None, int | None] | None = None
    min_size: int | None = None
    match_regex: str | None = None
    match_glob: str | None = None
    date_bucket: bool = False
    priority: int = 0
    # compiled regex, populated during validation
    _regex: re.Pattern | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_dict(cls, d: dict) -> "RuleSpec":
        known = {
            "name",
            "destination",
            "extensions",
            "size_range",
            "min_size",
            "match_regex",
            "match_glob",
            "date_bucket",
            "priority",
        }
        unknown = set(d) - known
        if unknown:
            raise ConfigError(
                f"Unknown rule keys: {', '.join(sorted(unknown))}"
            )
        name = d.get("name")
        destination = d.get("destination")
        extensions = d.get("extensions")
        if extensions is not None:
            extensions = [str(e).lower().lstrip(".") for e in extensions]
        size_range = d.get("size_range")
        if size_range is not None:
            if not isinstance(size_range, (list, tuple)) or len(size_range) != 2:
                raise ConfigError(
                    f"size_range must be a [min, max] pair, got {size_range!r}"
                )
            lo, hi = size_range
            lo = parse_size(lo) if lo is not None else None
            hi = parse_size(hi) if hi is not None else None
            size_range = (lo, hi)
        min_size = d.get("min_size")
        if min_size is not None:
            min_size = parse_size(min_size)
        return cls(
            name=name,
            destination=destination,
            extensions=extensions,
            size_range=size_range,
            min_size=min_size,
            match_regex=d.get("match_regex"),
            match_glob=d.get("match_glob"),
            date_bucket=bool(d.get("date_bucket", False)),
            priority=int(d.get("priority", 0)),
        )

    @property
    def selector_count(self) -> int:
        count = 0
        if self.extensions:
            count += 1
        if self.size_range is not None:
            count += 1
        if self.min_size is not None:
            count += 1
        if self.match_regex is not None:
            count += 1
        if self.match_glob is not None:
            count += 1
        return count

    @property
    def is_catch_all(self) -> bool:
        return self.selector_count == 0


@dataclass
class Config:
    options: Options
    rules: list[RuleSpec]

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        if d is None:
            d = {}
        known = {"options", "rules"}
        unknown = set(d) - known
        if unknown:
            raise ConfigError(
                f"Unknown top-level keys: {', '.join(sorted(unknown))}"
            )
        options = Options.from_dict(d.get("options", {}) or {})
        raw_rules = d.get("rules", []) or []
        if not isinstance(raw_rules, list):
            raise ConfigError("'rules' must be a list")
        rules = [RuleSpec.from_dict(r) for r in raw_rules]
        cfg = cls(options=options, rules=rules)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        seen = set()
        for rule in self.rules:
            if not rule.name or not str(rule.name).strip():
                raise ConfigError("Every rule needs a non-empty name")
            if rule.name in seen:
                raise ConfigError(f"Duplicate rule name: {rule.name!r}")
            seen.add(rule.name)
            if not rule.destination or not str(rule.destination).strip():
                raise ConfigError(
                    f"Rule {rule.name!r} needs a non-empty destination"
                )
            if rule.match_regex is not None:
                try:
                    rule._regex = re.compile(rule.match_regex)
                except re.error as exc:
                    raise ConfigError(
                        f"Rule {rule.name!r} has an invalid regex: {exc}"
                    ) from exc

    @classmethod
    def default(cls) -> "Config":
        """A sensible default config keyed on common extensions."""
        rules = [
            RuleSpec(
                name="images",
                destination="{source}/Images/{year}/{month}",
                extensions=["jpg", "jpeg", "png", "gif", "heic"],
                date_bucket=True,
                priority=10,
            ),
            RuleSpec(
                name="documents",
                destination="{source}/Documents",
                extensions=["pdf", "doc", "docx", "txt", "md"],
                priority=10,
            ),
            RuleSpec(
                name="video",
                destination="{source}/Video",
                extensions=["mp4", "mov", "mkv"],
                priority=10,
            ),
            RuleSpec(
                name="audio",
                destination="{source}/Audio",
                extensions=["mp3", "wav", "flac", "aac"],
                priority=10,
            ),
            RuleSpec(
                name="archives",
                destination="{source}/Archives",
                extensions=["zip", "tar", "gz", "7z", "rar"],
                priority=10,
            ),
            RuleSpec(
                name="by-size-fallback",
                destination="{source}/Other/{size_bucket}",
                priority=0,
            ),
        ]
        cfg = cls(options=Options(), rules=rules)
        cfg.validate()
        return cfg

    def with_overrides(self, **overrides) -> "Config":
        """Return a copy with option overrides applied (CLI beats config)."""
        opts = replace(
            self.options,
            **{k: v for k, v in overrides.items() if v is not None},
        )
        return Config(options=opts, rules=list(self.rules))


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Cannot parse YAML config {path}: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config root must be a mapping in {path}")
    return Config.from_dict(data)
