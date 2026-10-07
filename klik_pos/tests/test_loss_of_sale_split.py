"""The Loss of Sale split rule, without a database."""

import unittest

from klik_pos.overrides.loss_of_sale import fold_los_into_quantity, in_stock_total, split_lines

A = ("ITEM-A", "Stores")


def line(requested, factor=1, whole=False, key=A):
	return {"key": key, "requested": requested, "factor": factor, "whole": whole}


class TestSplitLines(unittest.TestCase):
	def test_partial_shortage_sells_what_is_there(self):
		self.assertEqual(split_lines([line(16)], {A: 10}), [(10, 6)])

	def test_enough_stock_changes_nothing(self):
		self.assertEqual(split_lines([line(4)], {A: 10}), [(4, 0)])

	def test_no_stock_keeps_a_zero_line(self):
		self.assertEqual(split_lines([line(6)], {}), [(0, 6)])

	def test_two_lines_share_the_stock_in_order(self):
		self.assertEqual(split_lines([line(7), line(7)], {A: 10}), [(7, 0), (3, 4)])

	def test_conversion_factor_counts_stock_units(self):
		# 2 boxes of 6 asked, 9 units held: 1.5 boxes in a UOM that allows fractions
		self.assertEqual(split_lines([line(2, factor=6)], {A: 9}), [(1.5, 0.5)])

	def test_whole_number_uom_floors_to_whole_units(self):
		# 2 boxes of 6 asked, 10 units held: one whole box sells
		self.assertEqual(split_lines([line(2, factor=6, whole=True)], {A: 10}), [(1, 1)])

	def test_negative_stock_counts_as_none(self):
		self.assertEqual(split_lines([line(3)], {A: -5}), [(0, 3)])

	def test_running_it_again_on_its_own_result_is_a_no_op(self):
		qty, los = split_lines([line(16)], {A: 10})[0]
		self.assertEqual(split_lines([line(qty + los)], {A: 10}), [(qty, los)])


class TestFold(unittest.TestCase):
	def test_a_held_order_keeps_what_was_asked_for(self):
		items = [{"id": "X", "quantity": 10, "los_qty": 6}, {"id": "Y", "quantity": 0, "los_qty": 3}]
		self.assertEqual(
			[(i["quantity"], i["los_qty"]) for i in fold_los_into_quantity(items)], [(16, 0), (3, 0)]
		)


B = ("ITEM-B", "Stores")


def priced(requested, rate, key=A, eligible=True):
	return {**line(requested, key=key), "rate": rate, "eligible": eligible}


class TestInStockTotal(unittest.TestCase):
	def test_a_held_order_comes_to_what_is_in_stock(self):
		# SO-00582: 10 belts at 100 with none in stock, 1 filter at 450 in stock.
		self.assertEqual(in_stock_total(1450, [priced(10, 100), priced(1, 450, key=B)], {B: 5}), 450)

	def test_taxes_and_discounts_scale_with_the_share_in_stock(self):
		# 1,160 is the order with tax; half of its value is in stock.
		self.assertEqual(in_stock_total(1160, [priced(2, 500)], {A: 1}), 580)

	def test_a_line_loss_of_sale_cannot_touch_counts_in_full(self):
		self.assertEqual(in_stock_total(300, [priced(3, 100, eligible=False)], {}), 300)

	def test_lines_of_one_item_share_its_stock(self):
		self.assertEqual(in_stock_total(400, [priced(2, 100), priced(2, 100)], {A: 3}), 300)

	def test_an_order_worth_nothing_stays_as_it_is(self):
		self.assertEqual(in_stock_total(0, [priced(1, 0)], {}), 0)
