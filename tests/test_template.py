from datetime import datetime
from pathlib import Path

import pytest

from file_organizer.errors import RuleError
from file_organizer.models import DateBasis, FileInfo
from file_organizer.template import resolve


def make_fi(name, size=100, created=None, modified=None):
    # 2021-03-15 and 2022-07-09
    created = created if created is not None else datetime(2021, 3, 15).timestamp()
    modified = modified if modified is not None else datetime(2022, 7, 9).timestamp()
    p = Path("/tmp") / name
    return FileInfo(
        path=p,
        size=size,
        created=created,
        modified=modified,
        is_symlink=False,
        ext=p.suffix.lower().lstrip("."),
    )


ROOT = Path("/data")


def test_source_and_name_and_ext():
    fi = make_fi("photo.JPG")
    out = resolve("{source}/{ext}/{name}", fi, ROOT, DateBasis.MODIFIED)
    assert out == Path("/data/jpg/photo").absolute()


def test_year_month_modified():
    fi = make_fi("a.jpg")
    out = resolve("{source}/{year}/{month}", fi, ROOT, DateBasis.MODIFIED)
    assert out == Path("/data/2022/07").absolute()


def test_year_month_created():
    fi = make_fi("a.jpg")
    out = resolve("{source}/{year}/{month}", fi, ROOT, DateBasis.CREATED)
    assert out == Path("/data/2021/03").absolute()


def test_month_name_and_day():
    fi = make_fi("a.jpg")
    out = resolve("{month_name}/{day}", fi, ROOT, DateBasis.MODIFIED)
    assert out == Path("July/09").absolute()


def test_size_bucket_placeholder():
    small = resolve("{size_bucket}", make_fi("a.x", size=10), ROOT, DateBasis.MODIFIED)
    assert small == Path("small").absolute()
    large = resolve(
        "{size_bucket}", make_fi("a.x", size=200 * 1024**2), ROOT, DateBasis.MODIFIED
    )
    assert large == Path("large").absolute()


def test_rule_placeholder():
    fi = make_fi("a.jpg")
    out = resolve("{source}/{rule}", fi, ROOT, DateBasis.MODIFIED, rule_name="images")
    assert out == Path("/data/images").absolute()


def test_unknown_placeholder_raises():
    fi = make_fi("a.jpg")
    with pytest.raises(RuleError):
        resolve("{source}/{bogus}", fi, ROOT, DateBasis.MODIFIED)


def test_unicode_preserved():
    fi = make_fi("café.jpg")
    out = resolve("{source}/{name}", fi, ROOT, DateBasis.MODIFIED)
    assert out.name == "café"
