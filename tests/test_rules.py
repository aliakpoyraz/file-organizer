from pathlib import Path

from file_organizer.config import RuleSpec
from file_organizer.models import FileInfo, SizeBucket
from file_organizer.rules import RuleEngine, size_bucket


def make_fi(name, size=100, ext=None):
    p = Path("/tmp") / name
    if ext is None:
        ext = p.suffix.lower().lstrip(".")
    return FileInfo(
        path=p, size=size, created=0.0, modified=0.0, is_symlink=False, ext=ext
    )


def test_extension_match():
    eng = RuleEngine([RuleSpec(name="img", destination="d", extensions=["jpg"])])
    assert eng.match(make_fi("a.jpg")).name == "img"
    assert eng.match(make_fi("a.png")) is None


def test_lowercase_ext_match():
    eng = RuleEngine([RuleSpec(name="img", destination="d", extensions=["jpg"])])
    assert eng.match(make_fi("A.JPG")).name == "img"


def test_size_range():
    eng = RuleEngine(
        [RuleSpec(name="mid", destination="d", size_range=(100, 200))]
    )
    assert eng.match(make_fi("a.x", size=150)).name == "mid"
    assert eng.match(make_fi("a.x", size=50)) is None
    assert eng.match(make_fi("a.x", size=250)) is None


def test_size_range_open_sides():
    eng = RuleEngine(
        [RuleSpec(name="big", destination="d", size_range=(100, None))]
    )
    assert eng.match(make_fi("a.x", size=99999)).name == "big"
    assert eng.match(make_fi("a.x", size=1)) is None


def test_min_size():
    eng = RuleEngine([RuleSpec(name="big", destination="d", min_size=1000)])
    assert eng.match(make_fi("a.x", size=2000)).name == "big"
    assert eng.match(make_fi("a.x", size=500)) is None


def test_regex_match():
    eng = RuleEngine(
        [RuleSpec(name="shot", destination="d", match_regex="^Screenshot.*")]
    )
    assert eng.match(make_fi("Screenshot 1.png")).name == "shot"
    assert eng.match(make_fi("photo.png")) is None


def test_glob_match():
    eng = RuleEngine(
        [RuleSpec(name="g", destination="d", match_glob="IMG_*.jpg")]
    )
    assert eng.match(make_fi("IMG_001.jpg")).name == "g"
    assert eng.match(make_fi("other.jpg")) is None


def test_first_match_and_priority_beats_order():
    rules = [
        RuleSpec(name="low", destination="d", extensions=["jpg"], priority=0),
        RuleSpec(name="high", destination="d", extensions=["jpg"], priority=10),
    ]
    eng = RuleEngine(rules)
    # despite low being first in config, high priority wins
    assert eng.match(make_fi("a.jpg")).name == "high"


def test_specificity_tiebreak():
    rules = [
        RuleSpec(name="catch", destination="d", priority=5),
        RuleSpec(
            name="specific",
            destination="d",
            extensions=["jpg"],
            min_size=1,
            priority=5,
        ),
    ]
    eng = RuleEngine(rules)
    # same priority; more selectors wins
    assert eng.match(make_fi("a.jpg", size=100)).name == "specific"


def test_config_order_stable_tiebreak():
    rules = [
        RuleSpec(name="first", destination="d", extensions=["jpg"], priority=1),
        RuleSpec(name="second", destination="d", extensions=["jpg"], priority=1),
    ]
    eng = RuleEngine(rules)
    assert eng.match(make_fi("a.jpg")).name == "first"


def test_catch_all():
    eng = RuleEngine([RuleSpec(name="all", destination="d")])
    assert eng.match(make_fi("anything.xyz")).name == "all"


def test_no_match_returns_none():
    eng = RuleEngine([RuleSpec(name="img", destination="d", extensions=["jpg"])])
    assert eng.match(make_fi("a.txt")) is None


def test_and_of_selectors():
    eng = RuleEngine(
        [
            RuleSpec(
                name="both",
                destination="d",
                extensions=["zip"],
                min_size=1000,
            )
        ]
    )
    assert eng.match(make_fi("a.zip", size=2000)).name == "both"
    # ext matches but size fails -> no match
    assert eng.match(make_fi("a.zip", size=100)) is None


def test_size_bucket():
    assert size_bucket(500) == SizeBucket.SMALL
    assert size_bucket(1024**2) == SizeBucket.SMALL
    assert size_bucket(5 * 1024**2) == SizeBucket.MEDIUM
    assert size_bucket(200 * 1024**2) == SizeBucket.LARGE
