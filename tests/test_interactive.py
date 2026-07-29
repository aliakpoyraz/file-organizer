"""Tests for the interactive ``fo`` menu.

questionary is replaced by a scripted stub that pops canned answers in call
order, so the whole flow runs without a TTY.
"""

from __future__ import annotations

import pytest

from file_organizer import interactive


class _Q:
    def __init__(self, val):
        self._val = val

    def ask(self):
        return self._val


class _Scripted:
    """Every prompt type returns the next queued answer, ignoring kwargs."""

    def __init__(self, answers):
        self._answers = list(answers)

    def _next(self, *args, **kwargs):
        return _Q(self._answers.pop(0))

    select = path = confirm = text = _next


@pytest.fixture
def script(monkeypatch):
    def _install(answers):
        monkeypatch.setattr(interactive, "questionary", _Scripted(answers))
    return _install


def _make_tree(tmp_path):
    (tmp_path / "note.txt").write_text("hi", encoding="utf-8")
    (tmp_path / "pic.jpg").write_bytes(b"\xff\xd8\xff\x00")
    return tmp_path


def test_ask_cancel_raises(script):
    script([None])
    with pytest.raises(interactive._Cancelled):
        interactive._ask(interactive.questionary.select("x", choices=[]))


def test_organize_confirmed(script, tmp_path):
    _make_tree(tmp_path)
    script([str(tmp_path), True])  # folder, proceed
    interactive._action_organize()
    assert not (tmp_path / "note.txt").exists()
    assert (tmp_path / "Documents" / "note.txt").exists()


def test_organize_declined(script, tmp_path):
    _make_tree(tmp_path)
    script([str(tmp_path), False])  # folder, proceed=No
    interactive._action_organize()
    assert (tmp_path / "note.txt").exists()


def test_organize_empty_folder(script, tmp_path):
    script([str(tmp_path)])  # nothing to move -> no confirm asked
    interactive._action_organize()  # should not raise


def test_undo_nothing(script, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    interactive._action_undo()  # no log -> "nothing to undo", no prompt


def test_undo_roundtrip(script, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # default undo log resolves inside tmp_path
    _make_tree(tmp_path)
    script([str(tmp_path), True])  # organize: folder, proceed
    interactive._action_organize()
    assert (tmp_path / "Documents" / "note.txt").exists()

    monkeypatch.setattr(interactive, "questionary", _Scripted([True]))  # undo: apply
    interactive._action_undo()
    assert (tmp_path / "note.txt").exists()


def _fake_menu(monkeypatch, keys):
    """Patch the full-screen menu to return queued keys (None = quit)."""
    queue = list(keys)
    monkeypatch.setattr(interactive, "_run_menu", lambda items: queue.pop(0))


def test_menu_quit(monkeypatch):
    _fake_menu(monkeypatch, [None])
    interactive._menu_loop()


def test_menu_runs_action_then_quits(script, tmp_path, monkeypatch):
    _make_tree(tmp_path)
    _fake_menu(monkeypatch, ["organize", None])
    # organize action prompts (questionary): folder, proceed, then "Menüye dön?"
    script([str(tmp_path), True, True])
    interactive._menu_loop()
    assert (tmp_path / "Documents" / "note.txt").exists()


@pytest.mark.parametrize(
    "keys, expected",
    [
        ("q", None),           # Q quits
        ("\x1b", None),        # Esc quits
        ("1", "organize"),     # number shortcut
        ("2", "undo"),
        ("\r", "organize"),    # Enter on default selection
        ("\x1b[B\r", "undo"),  # Down then Enter
        ("\x1b[B\x1b[B\r", "organize"),  # wraps around
    ],
)
def test_run_menu_keybindings(keys, expected):
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    items = [(k, label, desc) for k, label, desc, _ in interactive._MENU]
    with create_pipe_input() as inp:
        with create_app_session(input=inp, output=DummyOutput()):
            inp.send_text(keys)
            assert interactive._run_menu(items) == expected


def test_main_without_questionary(monkeypatch):
    monkeypatch.setattr(interactive, "questionary", None)
    with pytest.raises(SystemExit):
        interactive.main()
