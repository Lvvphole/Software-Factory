"""Tiny calculator. Contains a deliberate bug for the Software Factory demo."""


def add(a: int, b: int) -> int:
    # BUG: should be a + b. Coding executor should fix this.
    return a - b


def mul(a: int, b: int) -> int:
    return a * b
