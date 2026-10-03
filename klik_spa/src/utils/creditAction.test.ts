import { describe, expect, it } from "vitest";
import { creditChoices } from "./creditAction";

describe("creditChoices", () => {
	it("named customers may keep or exchange", () => {
		expect(creditChoices(false, false)).toEqual(["keep", "exchange"]);
	});

	it("walk-in has no till choices without an override", () => {
		expect(creditChoices(true, false)).toEqual([]);
	});

	it("a manager override restores keep for walk-in", () => {
		expect(creditChoices(true, true)).toEqual(["keep", "exchange"]);
	});
});
