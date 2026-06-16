from calculator import add, mul


def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(10, 20) == 30


def test_mul():
    assert mul(2, 3) == 6
