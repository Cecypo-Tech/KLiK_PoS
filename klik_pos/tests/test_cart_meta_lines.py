import unittest

from klik_pos.api.sales_order import _build_cart_meta, line_meta


class TestCartMetaLines(unittest.TestCase):
	def test_two_lines_of_one_item_keep_their_own_state(self):
		items = [
			{"id": "PEN", "line_id": "PEN", "discountAmount": 1},
			{"id": "PEN", "line_id": "PEN-1731", "discountAmount": 3},
		]
		data = {"itemDiscounts": {"PEN": {"customRate": 9}, "PEN-1731": {"customRate": 7}}}
		meta = _build_cart_meta(data, items, "B2C", None, None, 0, None, None, 0)
		self.assertEqual([line_meta(meta, i, "PEN")["discountAmount"] for i in (0, 1)], [1, 3])
		self.assertEqual([line_meta(meta, i, "PEN")["customRate"] for i in (0, 1)], [9, 7])

	def test_older_meta_falls_back_to_item_code(self):
		self.assertEqual(line_meta({"itemDiscounts": {"PEN": {"discountAmount": 2}}}, 0, "PEN")["discountAmount"], 2)
