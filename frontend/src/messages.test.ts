import { describe, expect, it } from "vitest";
import en from "../messages/en.json";
import pt from "../messages/pt-PT.json";

/** The placeholders a message fills in, such as {version}. */
function placeholders(message: string): string[] {
  return [...message.matchAll(/\{(\w+)\}/g)].map((found) => found[1]).sort();
}

describe("the message catalogues", () => {
  it("translate every English message into Portuguese and nothing else", () => {
    expect(Object.keys(pt).sort()).toEqual(Object.keys(en).sort());
  });

  it("fill in the same placeholders in both languages", () => {
    for (const [key, message] of Object.entries(en)) {
      if (key === "$schema") continue;
      expect(placeholders(pt[key as keyof typeof pt]), key).toEqual(placeholders(message));
    }
  });
});
