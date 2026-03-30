from myapp.calculator import add, evaluate


def test_add():
    assert add(1, 2) == 3


def test_evaluate():
    assert evaluate("1 + 2") == 3
