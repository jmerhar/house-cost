/**
 * The interface's language: the person's own choice, or else the first of the browser's
 * languages the interface has, or else English. jigkit's i18n module runs the choice over this
 * interface's Paraglide runtime; the strategies it defines are the ones build/paraglide.ts lists.
 */

import { createLanguage } from "@jmerhar/jigkit/i18n";
import * as runtime from "../paraglide/runtime.js";
import type { Locale } from "../paraglide/runtime.js";

/** Where the person's choice of language is kept. */
export const LANGUAGE_KEY = "house-cost-language";

/** Each language's name, in that language, as the language menu offers it. */
export const LANGUAGE_NAMES: Record<Locale, string> = { en: "English", "pt-PT": "Português" };

/** English writes dates and numbers with the day first and a 24-hour clock. */
const language = createLanguage(runtime, { storageKey: LANGUAGE_KEY, intl: { en: "en-GB" } });

export const useLanguageStrategies = language.useStrategies;
export const chosenLanguage = language.chosen;
export const chooseLanguage = language.choose;
/** Settles the language for as long as the page is open, and names it on <html lang>. */
export const settleLanguage = (): Locale => language.settle();
export const intlLocale = language.intlLocale;
