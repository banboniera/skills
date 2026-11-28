import unittest
from unittest.mock import patch

from src.poster import render_title


class RenderTitleTests(unittest.TestCase):
    def test_unset_keeps_title_case(self):
        with patch.dict("os.environ", clear=True):
            self.assertEqual(render_title("Open"), "O p e n")

    def test_true_selects_uppercase(self):
        with patch.dict("os.environ", {"POSTER_UPPERCASE": "true"}):
            self.assertEqual(render_title("Open"), "O P E N")
