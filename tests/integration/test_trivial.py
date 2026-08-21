import pytest


@pytest.mark.integration
def test_trivial_integration() -> None:
    assert 1 + 1 == 2
