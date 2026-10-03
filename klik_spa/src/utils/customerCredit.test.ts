import { describe, expect, it } from "vitest";
import { allocateCredit } from "./customerCredit";

describe("allocateCredit", () => {
	const notes = [
		{ invoice: "X-POS-00001", available: 40 },
		{ invoice: "X-POS-00002", available: 100 },
	];

	it("fills oldest note first", () => {
		expect(allocateCredit(notes, 30)).toEqual([{ invoice: "X-POS-00001", amount: 30 }]);
	});

	it("spills into the next note and stops at the target", () => {
		expect(allocateCredit(notes, 90)).toEqual([
			{ invoice: "X-POS-00001", amount: 40 },
			{ invoice: "X-POS-00002", amount: 50 },
		]);
	});

	it("never exceeds what the notes hold", () => {
		expect(allocateCredit(notes, 500)).toEqual([
			{ invoice: "X-POS-00001", amount: 40 },
			{ invoice: "X-POS-00002", amount: 100 },
		]);
	});

	it("rounds to cents", () => {
		expect(allocateCredit([{ invoice: "N", available: 10.005 }], 10.004)).toEqual([
			{ invoice: "N", amount: 10 },
		]);
	});
});
