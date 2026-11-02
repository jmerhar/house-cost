import { catalogueProblems } from "@jmerhar/jigkit/i18n/testing";
import { expect, it } from "vitest";
import en from "../messages/en.json";
import pt from "../messages/pt-PT.json";

it("translates every English message into Portuguese, with the same placeholders", () => {
  expect(catalogueProblems({ en, "pt-PT": pt })).toEqual([]);
});
