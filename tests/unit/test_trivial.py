import pytest


@pytest.mark.unit
def test_trivial_unit() -> None:
    assert 1 + 1 == 2
