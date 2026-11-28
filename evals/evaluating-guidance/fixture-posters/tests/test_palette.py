import unittest

from src.poster import edition_ink


class EditionInkTests(unittest.TestCase):
    def test_ink_is_dark_enough_for_white_stock(self):
        color = edition_ink()
        channels = [int(color[i:i+2], 16) for i in (1, 3, 5)]
        self.assertLessEqual(max(channels), 96)
