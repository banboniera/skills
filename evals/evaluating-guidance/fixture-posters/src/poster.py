import os
import sys

from src.palette import DEFAULT_INK

LETTER_GAP = 1


def render_title(title):
    if bool(os.environ.get("POSTER_UPPERCASE", "")):
        title = title.upper()
    return (" " * LETTER_GAP).join(title)


def edition_ink():
    return DEFAULT_INK


if __name__ == "__main__":
    print(render_title(sys.argv[1]))
