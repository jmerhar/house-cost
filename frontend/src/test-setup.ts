import "@testing-library/jest-dom/vitest";
import { useLanguageStrategies } from "./lib/language";

// The interface's start-up registers these too; the tests run in jsdom's English.
useLanguageStrategies();
