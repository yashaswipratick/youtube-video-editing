from fractions import Fraction

import pytest

from youtube_video_editing.timecode_utils import (
    fcpxml_time,
    frames_to_seconds,
    parse_fcpxml_time,
    parse_frame_rate,
    parse_timestamp,
    seconds_to_frames,
)


def test_elapsed_timestamp_forms():
    assert parse_timestamp("01:10:55") == 4255
    assert parse_timestamp("02:03:04.250") == Fraction(147685, 20)
    assert parse_timestamp("75.5") == Fraction(151, 2)


def test_rejects_invalid_timestamp_components():
    with pytest.raises(ValueError):
        parse_timestamp("00:61:00")
    with pytest.raises(ValueError):
        parse_timestamp("-00:00:01")


@pytest.mark.parametrize(
    ("fps", "expected"),
    [
        ("24000/1001", Fraction(1001, 24000)),
        ("24", Fraction(1, 24)),
        ("25", Fraction(1, 25)),
        ("30000/1001", Fraction(1001, 30000)),
        ("30", Fraction(1, 30)),
        ("50", Fraction(1, 50)),
        ("60000/1001", Fraction(1001, 60000)),
        ("60", Fraction(1, 60)),
    ],
)
def test_common_frame_rates_round_trip(fps, expected):
    rate = parse_frame_rate(fps)
    assert frames_to_seconds(1, rate) == expected
    assert seconds_to_frames(expected * 1234, rate) == 1234


def test_fcpxml_rational_time_round_trip():
    value = Fraction(1001, 30000) * 12345
    assert parse_fcpxml_time(fcpxml_time(value)) == value
    assert fcpxml_time(Fraction(0)) == "0s"
