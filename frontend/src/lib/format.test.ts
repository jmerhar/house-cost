import { describe, expect, it } from "vitest";
import {
  amountInput,
  day,
  euros,
  fileSize,
  moment,
  monthName,
  parseAmount,
  parsePercent,
  percent,
  percentInput,
  today,
} from "./format";

const nbsp = (text: string) => text.replace(/[\u00a0\u202f]/g, " ");

describe("euros", () => {
  it("writes euros as each language does", () => {
    expect(euros(32269, "en-GB")).toBe("€322.69");
    expect(nbsp(euros(32269, "pt-PT"))).toBe("322,69 €");
    expect(euros(-501, "en-GB")).toBe("-€5.01");
  });

  it("follows the interface's language by default", () => {
    expect(euros(100)).toBe("€1.00");
  });
});

describe("amountInput", () => {
  it("shows cents as a plain number to edit", () => {
    expect(amountInput(32269, "en-GB")).toBe("322.69");
    expect(amountInput(123456, "pt-PT")).toBe("1234,56");
    expect(amountInput(-5)).toBe("-0.05");
  });
});

describe("parseAmount", () => {
  it.each([
    ["322,69", 32269],
    ["322.69", 32269],
    ["322", 32200],
    ["322,5", 32250],
    ["0,05", 5],
    [",5", 50],
    ["1.234,56", 123456],
    ["1,234.56", 123456],
    ["1 234,56", 123456],
    ["1.234", 123400],
    ["1.234.567", 123456700],
    ["€ 12,50", 1250],
    ["12,50 €", 1250],
    ["-5", -500],
    ["−3,10", -310],
  ])("reads %s as %i cents", (text, cents) => {
    expect(parseAmount(text)).toBe(cents);
  });

  it.each(["", "abc", "1,2,3.4.5", "12,345,6", "12.3456", "1e5", "--1", "€", "1,234.567", "12,34.5", "1.2345,6"])(
    "refuses %s",
    (text) => {
      expect(parseAmount(text)).toBeNull();
    },
  );

  it("refuses an amount too large to be exact", () => {
    expect(parseAmount("99999999999999999")).toBeNull();
  });
});

describe("percentages", () => {
  it("writes basis points as a percentage", () => {
    expect(percent(5000, "en-GB")).toBe("50%");
    expect(percent(3333, "en-GB")).toBe("33.33%");
    expect(nbsp(percent(2500, "pt-PT"))).toBe("25%");
    expect(percentInput(3333)).toBe("33.33");
  });

  it.each([
    ["25", 2500],
    ["33,33", 3333],
    ["12.5%", 1250],
    ["100", 10000],
    [" 0 ", 0],
  ])("reads %s as %i basis points", (text, basisPoints) => {
    expect(parsePercent(text)).toBe(basisPoints);
  });

  it.each(["", "abc", "100.01", "150", "1.234", "-5"])("refuses %s", (text) => {
    expect(parsePercent(text)).toBeNull();
  });
});

describe("dates", () => {
  it("writes a day as each language does, day first", () => {
    expect(day("2026-10-23", "en-GB")).toBe("23 Oct 2026");
    expect(day("2026-07-06", "pt-PT")).toBe("6/07/2026");
  });

  it("writes a moment with its time", () => {
    expect(moment("2026-10-23T14:05:00Z", "en-GB")).toMatch(/23 Oct 2026, \d\d:\d\d/);
  });

  it("names months", () => {
    expect(monthName(10, "en-GB")).toBe("October");
    expect(monthName(1, "pt-PT")).toBe("janeiro");
  });

  it("knows today in the person's own time zone", () => {
    expect(today(new Date(2026, 9, 26, 23, 30))).toBe("2026-10-26");
  });
});

describe("fileSize", () => {
  it("writes a size in kilobytes or megabytes", () => {
    expect(fileSize(312_000, "en-GB")).toBe("312 kB");
    expect(fileSize(200, "en-GB")).toBe("1 kB");
    expect(fileSize(2_450_000, "en-GB")).toBe("2.5 MB");
  });
});
