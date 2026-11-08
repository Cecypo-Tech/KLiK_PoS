import unittest

from klik_pos.api.sales_invoice import parse_invoice_data
from klik_pos.api.sales_order import _build_cart_meta, line_meta


def _parsed_items(data):
	out = parse_invoice_data(data)
	return next(x for x in (out if isinstance(out, (list, tuple)) else [out]) if isinstance(x, list) and x and isinstance(x[0], dict) and "quantity" in x[0])


class TestCartMetaLines(unittest.TestCase):
	def test_two_lines_of_one_item_keep_their_own_state(self):
		# Through the parser, as every caller does: it must keep each line's id.
		data = {
			"customer": {"id": "x"},
			"items": [
				{"id": "PEN", "item_code": "PEN", "line_id": "PEN", "quantity": 1, "price": 10, "discountAmount": 1},
				{"id": "PEN", "item_code": "PEN", "line_id": "PEN-1731", "quantity": 1, "price": 8, "discountAmount": 3},
			],
			"itemDiscounts": {"PEN": {"customRate": 9}, "PEN-1731": {"customRate": 7}},
		}
		parsed = _parsed_items(data)
		self.assertEqual([i["line_id"] for i in parsed], ["PEN", "PEN-1731"])
		meta = _build_cart_meta(data, parsed, "B2C", None, None, 0, None, None, 0)
		self.assertEqual([line_meta(meta, i, "PEN")["discountAmount"] for i in (0, 1)], [1, 3])
		self.assertEqual([line_meta(meta, i, "PEN")["customRate"] for i in (0, 1)], [9, 7])

	def test_older_meta_falls_back_to_item_code(self):
		self.assertEqual(line_meta({"itemDiscounts": {"PEN": {"discountAmount": 2}}}, 0, "PEN")["discountAmount"], 2)
