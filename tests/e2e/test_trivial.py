import pytest


@pytest.mark.e2e
def test_trivial_e2e() -> None:
    assert 1 + 1 == 2
