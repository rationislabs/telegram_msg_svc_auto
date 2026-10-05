from datetime import date

from tgforecast import state


def test_round_trip(tmp_path):
    path = tmp_path / "sub" / "state.json"
    assert state.last_posted(path) is None
    state.mark_posted(path, date(2026, 10, 6))
    assert state.last_posted(path) == date(2026, 10, 6)
    assert not list(path.parent.glob("*.tmp")), "temp file left behind"


def test_corrupt_file_means_never_posted(tmp_path):
    path = tmp_path / "state.json"
    for junk in ("", "{", '{"last_posted": 7}', '{"other": "x"}', '["2026-10-06"]'):
        path.write_text(junk)
        assert state.last_posted(path) is None, junk
