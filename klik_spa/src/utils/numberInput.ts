/**
 * Number fields take a sum, the way ERPNext's do (frappe.utils.eval_expression): digits,
 * `+ - * / ( )`, decimal points and spaces; commas are thousands separators. Anything else
 * is not a number. Parsed here rather than eval'd, so nothing typed ever runs as code.
 */

const ALLOWED = /^[0-9+\-*/.() ]+$/;

export function evaluateNumber(text: string): number | undefined {
  const src = String(text ?? "").replace(/,/g, "").trim();
  if (!src || !ALLOWED.test(src)) return undefined;

  let pos = 0;
  const peek = () => { while (src[pos] === " ") pos++; return src[pos]; };

  // expr := term (('+'|'-') term)* ; term := factor (('*'|'/') factor)* ; factor := '-' factor | '(' expr ')' | number
  const expr = (): number => {
    let value = term();
    for (let op = peek(); op === "+" || op === "-"; op = peek()) {
      pos++;
      value = op === "+" ? value + term() : value - term();
    }
    return value;
  };
  const term = (): number => {
    let value = factor();
    for (let op = peek(); op === "*" || op === "/"; op = peek()) {
      pos++;
      const right = factor();
      if (op === "/" && right === 0) throw new Error("division by zero");
      value = op === "*" ? value * right : value / right;
    }
    return value;
  };
  const factor = (): number => {
    const c = peek();
    if (c === "-") { pos++; return -factor(); }
    if (c === "+") { pos++; return factor(); }
    if (c === "(") {
      pos++;
      const value = expr();
      if (peek() !== ")") throw new Error("missing )");
      pos++;
      return value;
    }
    const match = /^\d*\.?\d+|^\d+\./.exec(src.slice(pos));
    if (!match) throw new Error("number expected");
    pos += match[0].length;
    return parseFloat(match[0]);
  };

  try {
    const value = expr();
    if (peek() !== undefined) return undefined; // trailing text, e.g. "2+3)" or "2**3"
    // ponytail: 10 dp drops float noise (0.1*3); finer precision than any till field needs.
    return Number.isFinite(value) ? Math.round(value * 1e10) / 1e10 : undefined;
  } catch {
    return undefined;
  }
}

/** A sum, not just a number: what earns the live "= result" hint. */
export function isExpression(text: string): boolean {
  return /\d\s*[+\-*/]|[()]/.test(String(text ?? "").replace(/,/g, ""));
}

export type NumberKind = "money" | "percent" | "qty";

const FORMATS: Record<NumberKind, Intl.NumberFormatOptions> = {
  money: { minimumFractionDigits: 2, maximumFractionDigits: 2 },
  percent: { minimumFractionDigits: 2, maximumFractionDigits: 2 },
  qty: { minimumFractionDigits: 0, maximumFractionDigits: 3 },
};

/** How a field shows its number at rest (the till's own en-US grouping, as formatCurrencyWithSymbol). */
export function formatNumber(value: number, kind: NumberKind): string {
  return Number(value || 0).toLocaleString("en-US", FORMATS[kind]);
}

/** What a box commits: its number or sum, else nothing (so "2*" or "12abc" changes nothing).
 * Money keeps currency precision, as ERPNext rounds a currency field ("100/3" is 33.33). */
export function readNumber(text: string, kind: NumberKind): number | undefined {
  const n = evaluateNumber(text);
  return n !== undefined && kind === "money" ? Math.round(n * 100) / 100 : n;
}

/** What a box shows while editing: the plain number, without float noise (0.1+0.2 shows 0.3). */
export function plainNumber(value: number): string {
  return String(Number.isFinite(value) ? Number(value.toFixed(10)) : 0);
}
