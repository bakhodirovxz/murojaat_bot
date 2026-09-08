"""Faol Matrix ko'prigiga yagona kirish nuqtasi.

`notify` moduli Matrix'ga xabar yuborishi kerak, `matrix_bot` esa `notify` ning
render funksiyalarini ishlatadi. Aylanma importni oldini olish uchun ko'prik shu
kichkina modulda saqlanadi.
"""

_bridge = None


def set_bridge(bridge) -> None:
    global _bridge
    _bridge = bridge


def get():
    """Matrix sozlanmagan bo'lsa None."""
    return _bridge
