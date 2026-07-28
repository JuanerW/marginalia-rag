from src.api.routes.progress import _is_after


def test_position_ordering() -> None:
    assert _is_after(2, 0, 1, 999)
    assert _is_after(2, 10, 2, 9)
    assert not _is_after(2, 9, 2, 10)
    assert not _is_after(2, 10, 2, 10)
