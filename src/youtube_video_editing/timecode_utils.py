"""Exact elapsed-time and frame-rate utilities."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from fractions import Fraction


_TIMECODE_RE = re.compile(
    r"^(?:(?P<hours>\d+):)?(?P<minutes>\d{1,2}):(?P<seconds>\d{1,2}(?:\.\d+)?)$"
)


def as_fraction(value: object, *, field: str = "value") -> Fraction:
    """Convert decimal/rational input to Fraction without binary-float noise."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number, not a boolean")
    try:
        if isinstance(value, str) and "/" in value:
            return Fraction(value)
        return Fraction(Decimal(str(value)))
    except (InvalidOperation, ValueError, ZeroDivisionError, TypeError) as exc:
        raise ValueError(f"Invalid {field}: {value!r}") from exc


def parse_timestamp(value: object, *, field: str = "timestamp") -> Fraction:
    """Parse elapsed seconds, MM:SS[.fraction], or HH:MM:SS[.fraction]."""
    if isinstance(value, (int, float, Decimal, Fraction)) and not isinstance(value, bool):
        result = as_fraction(value, field=field)
    elif isinstance(value, str):
        text = value.strip()
        match = _TIMECODE_RE.fullmatch(text)
        if match:
            hours = int(match.group("hours") or 0)
            minutes = int(match.group("minutes"))
            seconds = as_fraction(match.group("seconds"), field=field)
            if minutes >= 60 or seconds >= 60:
                raise ValueError(
                    f"{field} has an invalid minutes/seconds component: {value!r}"
                )
            result = Fraction(hours * 3600 + minutes * 60, 1) + seconds
        else:
            result = as_fraction(text, field=field)
    else:
        raise ValueError(f"{field} must be a timestamp string or number")
    if result < 0:
        raise ValueError(f"{field} cannot be negative")
    return result


def parse_frame_rate(value: object, *, field: str = "frame rate") -> Fraction:
    rate = as_fraction(value, field=field)
    if rate <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return rate


def round_fraction(value: Fraction) -> int:
    """Round a non-negative fraction to nearest integer, ties away from zero."""
    if value < 0:
        return -round_fraction(-value)
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def seconds_to_frames(seconds: Fraction, fps: Fraction) -> int:
    return round_fraction(seconds * fps)


def frames_to_seconds(frames: int, fps: Fraction) -> Fraction:
    if fps <= 0:
        raise ValueError("Frame rate must be greater than zero")
    return Fraction(frames, 1) / fps


def fcpxml_time(value: Fraction) -> str:
    """Render a rational number of seconds in FCPXML time syntax."""
    if value == 0:
        return "0s"
    value = Fraction(value)
    if value.denominator == 1:
        return f"{value.numerator}s"
    return f"{value.numerator}/{value.denominator}s"


def parse_fcpxml_time(value: str) -> Fraction:
    text = value.strip()
    if not text.endswith("s"):
        raise ValueError(f"Unsupported FCPXML time value: {value!r}")
    return Fraction(text[:-1])


def format_timestamp(seconds: Fraction, *, milliseconds: bool = True) -> str:
    """Format a non-negative elapsed time as HH:MM:SS[.mmm]."""
    total_ms = round_fraction(Fraction(seconds) * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    base = f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}"
    if milliseconds:
        return f"{base}.{millis:03d}"
    return base


def rational_text(value: Fraction) -> str:
    value = Fraction(value)
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"
