from collections import Counter

from file_organizer.report import RunReport


def test_counters_and_bytes():
    r = RunReport()
    r.moved = 3
    r.skipped = 1
    r.failed = 2
    r.overwritten = 1
    r.bytes_moved = 4096
    r.by_rule = Counter({"images": 2, "docs": 1})
    d = r.as_dict()
    assert d["moved"] == 3
    assert d["by_rule"]["images"] == 2
    assert d["bytes_moved"] == 4096


def test_render_text():
    r = RunReport(moved=2, skipped=1)
    r.by_rule = Counter({"images": 2})
    text = r.render()
    assert "moved:" in text
    assert "images: 2" in text
    assert not text.startswith("DRY-RUN")


def test_render_dry_run_prefix():
    r = RunReport(dry_run=True)
    assert r.render().startswith("DRY-RUN")


def test_render_verbose_errors():
    r = RunReport(failed=1)
    r.errors = [("/a/b.txt", "boom")]
    text = r.render(verbose=True)
    assert "boom" in text
    # non-verbose hides errors
    assert "boom" not in r.render(verbose=False)


def test_as_dict_shape():
    r = RunReport()
    d = r.as_dict()
    assert set(d) == {
        "moved",
        "skipped",
        "failed",
        "overwritten",
        "dry_run",
        "by_rule",
        "bytes_moved",
        "errors",
    }
