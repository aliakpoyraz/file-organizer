"""Command-line interface (click)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from file_organizer import __version__
from file_organizer.config import Config, load_config
from file_organizer.errors import OrganizerError
from file_organizer.models import ConflictStrategy, DateBasis
from file_organizer.organizer import Organizer
from file_organizer.report import RunReport
from file_organizer.rules import RuleEngine
from file_organizer.undo import UndoLog

EXAMPLE_CONFIG = """\
options:
  dry_run: false
  watch: false
  undo_log: .file-organizer-undo.jsonl
  conflict_strategy: rename
  follow_symlinks: false
  date_basis: modified
  recursive: false

rules:
  - name: images
    extensions: [jpg, jpeg, png, gif, heic]
    destination: "{source}/Images/{year}/{month}"
    date_bucket: true
    priority: 10

  - name: documents
    extensions: [pdf, doc, docx, txt, md]
    destination: "{source}/Documents"
    priority: 10

  - name: video
    extensions: [mp4, mov, mkv]
    destination: "{source}/Video"
    priority: 10

  - name: large-archives
    extensions: [zip, tar, gz]
    min_size: 104857600
    destination: "{source}/Archives/large"
    priority: 20

  - name: screenshots
    match_regex: "^Screenshot.*"
    destination: "{source}/Images/Screenshots"
    priority: 30

  - name: by-size-fallback
    destination: "{source}/Other/{size_bucket}"
    priority: 0
"""


def _load_config(config_path: str | None) -> Config:
    if config_path:
        return load_config(config_path)
    return Config.default()


def _apply_overrides(cfg: Config, **kw) -> Config:
    overrides = {}
    if kw.get("dry_run"):
        overrides["dry_run"] = True
    if kw.get("conflict") is not None:
        overrides["conflict_strategy"] = ConflictStrategy(kw["conflict"])
    if kw.get("undo_log") is not None:
        overrides["undo_log"] = Path(kw["undo_log"])
    if kw.get("follow_symlinks") is not None:
        overrides["follow_symlinks"] = kw["follow_symlinks"]
    if kw.get("recursive") is not None:
        overrides["recursive"] = kw["recursive"]
    if kw.get("date_basis") is not None:
        overrides["date_basis"] = DateBasis(kw["date_basis"])
    if kw.get("no_verify"):
        overrides["verify_hash"] = False
    return cfg.with_overrides(**overrides)


def _emit(report: RunReport, *, as_json: bool, verbose: bool, quiet: bool) -> None:
    if as_json:
        click.echo(json.dumps(report.as_dict(), indent=2))
    elif not quiet:
        click.echo(report.render(verbose=verbose))


# Shared option decorators -------------------------------------------------
def common_options(func):
    func = click.option("-c", "--config", "config_path", type=click.Path(), default=None)(func)
    func = click.option("-n", "--dry-run", is_flag=True, default=False)(func)
    func = click.option(
        "--conflict", type=click.Choice(["rename", "skip", "overwrite"]), default=None
    )(func)
    func = click.option("--undo-log", type=click.Path(), default=None)(func)
    func = click.option(
        "--follow-symlinks/--no-follow-symlinks", default=None
    )(func)
    func = click.option("--recursive/--no-recursive", default=None)(func)
    func = click.option(
        "--date-basis", type=click.Choice(["created", "modified"]), default=None
    )(func)
    func = click.option("--no-verify", is_flag=True, default=False)(func)
    func = click.option("-v", "--verbose", is_flag=True, default=False)(func)
    func = click.option("-q", "--quiet", is_flag=True, default=False)(func)
    func = click.option("--json", "as_json", is_flag=True, default=False)(func)
    return func


@click.group()
@click.version_option(__version__)
def cli():
    """file-organizer: sort files into folders using configurable rules."""


def _run_organize(path, *, dry_run, config_path, conflict, undo_log,
                  follow_symlinks, recursive, date_basis, no_verify,
                  verbose, quiet, as_json):
    cfg = _load_config(config_path)
    cfg = _apply_overrides(
        cfg,
        dry_run=dry_run,
        conflict=conflict,
        undo_log=undo_log,
        follow_symlinks=follow_symlinks,
        recursive=recursive,
        date_basis=date_basis,
        no_verify=no_verify,
    )
    organizer = Organizer(cfg, RuleEngine(cfg.rules))
    actions = organizer.plan(path)

    log = None
    if not cfg.options.dry_run:
        log = UndoLog(cfg.options.undo_log)

    use_progress = not (quiet or as_json) and sys.stdout.isatty()
    if use_progress:
        with click.progressbar(actions, label="Organizing") as bar:
            report = organizer.execute(
                actions,
                dry_run=cfg.options.dry_run,
                progress_cb=lambda a: None,
                undo_log=log,
            )
            # advance bar fully
            for _ in bar:
                pass
    else:
        report = organizer.execute(
            actions, dry_run=cfg.options.dry_run, undo_log=log
        )
    _emit(report, as_json=as_json, verbose=verbose, quiet=quiet)
    return report


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@common_options
def organize(path, config_path, dry_run, conflict, undo_log, follow_symlinks,
             recursive, date_basis, no_verify, verbose, quiet, as_json):
    """Organize files in PATH according to the rules."""
    try:
        _run_organize(
            path, dry_run=dry_run, config_path=config_path, conflict=conflict,
            undo_log=undo_log, follow_symlinks=follow_symlinks,
            recursive=recursive, date_basis=date_basis, no_verify=no_verify,
            verbose=verbose, quiet=quiet, as_json=as_json,
        )
    except OrganizerError as exc:
        _fail(exc, verbose)


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@common_options
def preview(path, config_path, dry_run, conflict, undo_log, follow_symlinks,
            recursive, date_basis, no_verify, verbose, quiet, as_json):
    """Preview changes without touching the filesystem (dry-run)."""
    try:
        _run_organize(
            path, dry_run=True, config_path=config_path, conflict=conflict,
            undo_log=undo_log, follow_symlinks=follow_symlinks,
            recursive=recursive, date_basis=date_basis, no_verify=no_verify,
            verbose=verbose, quiet=quiet, as_json=as_json,
        )
    except OrganizerError as exc:
        _fail(exc, verbose)


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@common_options
def report(path, config_path, dry_run, conflict, undo_log, follow_symlinks,
           recursive, date_basis, no_verify, verbose, quiet, as_json):
    """Report what would happen (dry-run classification only)."""
    try:
        _run_organize(
            path, dry_run=True, config_path=config_path, conflict=conflict,
            undo_log=undo_log, follow_symlinks=follow_symlinks,
            recursive=recursive, date_basis=date_basis, no_verify=no_verify,
            verbose=verbose, quiet=quiet, as_json=as_json,
        )
    except OrganizerError as exc:
        _fail(exc, verbose)


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@common_options
@click.option("--settle", type=float, default=2.0, help="Settle seconds.")
def watch(path, config_path, dry_run, conflict, undo_log, follow_symlinks,
          recursive, date_basis, no_verify, verbose, quiet, as_json, settle):
    """Watch PATH and organize new files as they appear."""
    from file_organizer.watcher import Watcher

    try:
        cfg = _load_config(config_path)
        cfg = _apply_overrides(
            cfg, dry_run=dry_run, conflict=conflict, undo_log=undo_log,
            follow_symlinks=follow_symlinks, recursive=recursive,
            date_basis=date_basis, no_verify=no_verify,
        )
        organizer = Organizer(cfg, RuleEngine(cfg.rules))
        log = None if cfg.options.dry_run else UndoLog(cfg.options.undo_log)
        watcher = Watcher(
            organizer, path, settle_seconds=settle, undo_log=log
        )
        watcher.install_signal_handlers()
        if not quiet:
            click.echo(f"Watching {path} (Ctrl-C to stop)...")
        agg = watcher.run()
        _emit(agg, as_json=as_json, verbose=verbose, quiet=quiet)
    except OrganizerError as exc:
        _fail(exc, verbose)


@cli.command()
@click.option("-c", "--config", "config_path", type=click.Path(), default=None)
@click.option("--undo-log", type=click.Path(), default=None)
@click.option("-n", "--dry-run", is_flag=True, default=False)
@click.option("-v", "--verbose", is_flag=True, default=False)
@click.option("-q", "--quiet", is_flag=True, default=False)
@click.option("--json", "as_json", is_flag=True, default=False)
def undo(config_path, undo_log, dry_run, verbose, quiet, as_json):
    """Revert the most recent organize operation."""
    try:
        if undo_log is not None:
            log_path = Path(undo_log)
        else:
            cfg = _load_config(config_path)
            log_path = cfg.options.undo_log
        log = UndoLog(log_path)
        report_ = log.revert_last(dry_run=dry_run)
        _emit(report_, as_json=as_json, verbose=verbose, quiet=quiet)
    except OrganizerError as exc:
        _fail(exc, verbose)


@cli.command("init-config")
@click.option("-o", "--output", type=click.Path(), default="file-organizer.yaml")
def init_config(output):
    """Write an example configuration file."""
    out = Path(output)
    if out.exists():
        raise click.ClickException(f"Refusing to overwrite existing {out}")
    out.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    click.echo(f"Wrote example config to {out}")


def _fail(exc: OrganizerError, verbose: bool) -> None:
    if verbose:
        raise exc
    click.echo(f"Error: {exc}", err=True)
    raise SystemExit(1)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
