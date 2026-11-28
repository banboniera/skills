import unittest

from src.gallery import order_captions


class CaptionOrderTests(unittest.TestCase):
    def test_casefold_order_keeps_input_order_for_ties(self):
        self.assertEqual(
            order_captions(["Pearl", "amber", "pearl"]),
            ["amber", "Pearl", "pearl"],
        )
