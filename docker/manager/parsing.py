"""Portable console field parsing."""
import shlex


def text(value):
    value = value.strip()
    if value.startswith(('"', "'")):
        parts = shlex.split(value)
        if len(parts) != 1:
            raise ValueError("Enter one value, optionally quoted.")
        value = parts[0]
    if not value or any(ord(c) < 32 for c in value):
        raise ValueError("Enter a nonempty, printable value.")
    return value

