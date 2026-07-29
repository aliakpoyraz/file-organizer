"""Interactive terminal menu launched via the ``fo`` command.

Deliberately tiny: type ``fo``, pick a folder, files get sorted into folders,
and if it went wrong you undo it. The menu is a mole-style full-screen picker
with real key bindings (arrows, number keys, Q to quit).
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from file_organizer import __version__
from file_organizer.config import Config
from file_organizer.errors import OrganizerError, UndoError
from file_organizer.organizer import Organizer
from file_organizer.report import RunReport
from file_organizer.rules import RuleEngine
from file_organizer.undo import UndoLog

try:  # questionary powers the small yes/no + path prompts inside each action
    import questionary
    from questionary import Style
except ImportError:  # pragma: no cover - dependency guaranteed by pyproject
    questionary = None
    Style = None


# --- Branding --------------------------------------------------------------
FO_LOGO = [
    r"  ______   ____  ",
    r" |  ____| / __ \ ",
    r" | |__   | |  | |",
    r" |  __|  | |  | |",
    r" | |     | |__| |",
    r" |_|      \____/ ",
]

GITHUB_URL = "https://github.com/aliakpoyraz/file-organizer"
TAGLINE = "Sort your files, undo anytime."

ACCENT = "#7aa2f7"
CYAN = "#56b6c2"
DIM = "#565f89"
LINK = "#7d5fff"

STYLE = Style(
    [
        ("qmark", f"fg:{ACCENT} bold"),
        ("question", "bold"),
        ("pointer", f"fg:{ACCENT} bold"),
        ("highlighted", f"fg:{ACCENT} bold"),
        ("answer", f"fg:{ACCENT} bold"),
        ("instruction", f"fg:{DIM}"),
    ]
) if Style is not None else None


class _Cancelled(Exception):
    """Raised when the user aborts a prompt (Ctrl-C / Esc)."""


def _ask(prompt) -> object:
    answer = prompt.ask()
    if answer is None:
        raise _Cancelled
    return answer


def _confirm(message, default=True):
    return _ask(questionary.confirm(message, default=default, style=STYLE, qmark="›"))


def _folder() -> str:
    path = _ask(
        questionary.path(
            "Which folder?",
            default=str(Path.cwd()),
            only_directories=True,
            style=STYLE,
            qmark="›",
            validate=lambda p: True if Path(p).expanduser().is_dir() else "No such folder.",
        )
    )
    return str(Path(path).expanduser())


# --- Full-screen mole-style menu ------------------------------------------
def _banner_fragments() -> list[tuple[str, str]]:
    """FO logo with the github link + tagline to its right, then a subtitle."""
    gutter = max(len(ln) for ln in FO_LOGO) + 3
    side = {2: ("class:link", GITHUB_URL), 3: ("class:tag", TAGLINE)}
    out: list[tuple[str, str]] = []
    for i, ln in enumerate(FO_LOGO):
        out.append(("class:logo", ln.ljust(gutter)))
        if i in side:
            out.append(side[i])
        out.append(("", "\n"))
    out.append(("class:ver", f"  v{__version__}"))
    out.append(("", "\n"))
    return out


def _bar_fragments() -> list[tuple[str, str]]:
    sep = ("class:bar", "   ·   ")
    return [
        ("", "  "),
        ("class:key", "↑↓"), ("class:bar", " Navigate"), sep,
        ("class:key", "↵"), ("class:bar", " Select"), sep,
        ("class:key", "Q"), ("class:bar", " Quit"),
        ("", "\n"),
    ]


def _run_menu(items: list[tuple[str, str, str]]) -> str | None:
    """Render the menu and return the chosen key, or None if the user quits."""
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style as PTStyle

    state = {"sel": 0}
    count = len(items)
    width = max(len(label) for _, label, _ in items)

    def fragments():
        out = _banner_fragments()
        out.append(("", "\n"))
        for i, (_key, label, desc) in enumerate(items):
            selected = i == state["sel"]
            out.append(("class:pointer", " › ") if selected else ("", "   "))
            out.append(("class:num", f"{i + 1}. "))
            out.append(("class:sel" if selected else "class:label", label.ljust(width)))
            out.append(("class:desc", "   " + desc))
            out.append(("", "\n"))
        out.append(("", "\n"))
        out.extend(_bar_fragments())
        return out

    kb = KeyBindings()

    @kb.add("up")
    @kb.add("k")
    def _up(event):
        state["sel"] = (state["sel"] - 1) % count

    @kb.add("down")
    @kb.add("j")
    def _down(event):
        state["sel"] = (state["sel"] + 1) % count

    @kb.add("enter")
    def _enter(event):
        event.app.exit(result=items[state["sel"]][0])

    @kb.add("q")
    @kb.add("c-c")
    @kb.add("c-d")
    @kb.add("escape")
    def _quit(event):
        event.app.exit(result=None)

    def _make_jump(idx):
        def _jump(event):
            event.app.exit(result=items[idx][0])
        return _jump

    for i in range(count):
        kb.add(str(i + 1))(_make_jump(i))

    style = PTStyle.from_dict(
        {
            "logo": "#5fd75f bold",
            "link": f"{LINK} bold",
            "tag": CYAN,
            "sub": "bold",
            "ver": DIM,
            "pointer": f"{ACCENT} bold",
            "num": DIM,
            "label": "",
            "sel": f"{ACCENT} bold",
            "desc": CYAN,
            "bar": DIM,
            "key": f"{ACCENT} bold",
        }
    )
    app = Application(
        layout=Layout(HSplit([Window(FormattedTextControl(fragments, focusable=True))])),
        key_bindings=kb,
        style=style,
        full_screen=True,
        mouse_support=False,
    )
    return app.run()


# --- Core ------------------------------------------------------------------
def _run(cfg: Config, path: str, *, dry_run: bool) -> RunReport:
    cfg = cfg.with_overrides(dry_run=dry_run)
    organizer = Organizer(cfg, RuleEngine(cfg.rules))
    actions = organizer.plan(path)
    log = None if cfg.options.dry_run else UndoLog(cfg.options.undo_log)

    if not actions:
        return organizer.execute(actions, dry_run=cfg.options.dry_run, undo_log=log)

    if sys.stdout.isatty() and not cfg.options.dry_run:
        with click.progressbar(length=len(actions), label="  Moving") as bar:
            return organizer.execute(
                actions,
                dry_run=cfg.options.dry_run,
                progress_cb=lambda a: bar.update(1),
                undo_log=log,
            )
    return organizer.execute(actions, dry_run=cfg.options.dry_run, undo_log=log)


def _header(title: str) -> None:
    click.clear()
    click.secho(f"  FO · {title}", fg="cyan", bold=True)
    click.secho("  " + "─" * 40, fg="bright_black")
    click.echo()


def _action_organize() -> None:
    _header("Organize")
    path = _folder()
    cfg = Config.default()

    preview = _run(cfg, path, dry_run=True)
    if preview.moved == 0:
        click.secho("\n  Nothing to move — folder is already tidy.\n", fg="yellow")
        return

    click.secho(f"\n  {preview.moved} files will be sorted into folders.", fg="cyan")
    if not _confirm("  Proceed?"):
        click.secho("  Cancelled.", fg="yellow")
        return

    report = _run(cfg, path, dry_run=False)
    click.echo()
    click.echo(report.render())
    click.secho("  Something wrong? Choose 'Undo' from the menu.\n", fg="bright_black")


def _action_undo() -> None:
    _header("Undo")
    log = UndoLog(Config.default().options.undo_log)
    try:
        preview = log.revert_last(dry_run=True)
    except UndoError:
        click.secho("\n  Nothing to undo.\n", fg="yellow")
        return
    if preview.moved == 0:
        click.secho("\n  Nothing to undo.\n", fg="yellow")
        return

    click.secho(f"\n  The last run moved {preview.moved} files.", fg="cyan")
    if not _confirm("  Restore them all (empty folders are removed)?"):
        click.secho("  Cancelled.", fg="yellow")
        return
    report = log.revert_last(dry_run=False)
    click.echo()
    click.echo(report.render())


_MENU = [
    ("organize", "Organize", "sort files into folders by type", _action_organize),
    ("undo", "Undo", "revert the last organize run", _action_undo),
]


def _menu_loop() -> None:
    items = [(key, label, desc) for key, label, desc, _ in _MENU]
    handlers = {key: h for key, _, _, h in _MENU}
    while True:
        choice = _run_menu(items)
        if choice is None:
            click.secho("\n  Bye.\n", fg="cyan")
            return
        try:
            handlers[choice]()
        except _Cancelled:
            click.secho("\n  Cancelled.", fg="yellow")
        except OrganizerError as exc:
            click.secho(f"\n  Error: {exc}", fg="red", err=True)
        try:
            _confirm("Back to menu?")
        except _Cancelled:
            return


def main() -> None:
    if questionary is None:
        click.echo(
            "The interactive menu needs 'questionary': pip install questionary",
            err=True,
        )
        raise SystemExit(1)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        click.echo(
            "fo needs an interactive terminal. For scripts use the direct "
            "commands instead, e.g. 'file-organizer organize <folder>'.",
            err=True,
        )
        raise SystemExit(1)
    try:
        _menu_loop()
    except (KeyboardInterrupt, _Cancelled):
        click.echo()
        click.secho("  Exited.", fg="cyan")


if __name__ == "__main__":
    main()
