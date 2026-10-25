/**
 * The interface's language: the person's own choice, or else the first of the browser's
 * languages the interface has, or else English.
 *
 * Both are Paraglide strategies of the interface's own (build/paraglide.ts). Paraglide writes the
 * first language it resolves back into every strategy, so its built-in localStorage strategy
 * would keep a language read from the browser as though it had been chosen. These strategies
 * ignore that write: only `chooseLanguage` keeps a choice.
 */

import {
  baseLocale,
  defineCustomClientStrategy,
  getLocale,
  locales,
  overwriteGetLocale,
  type Locale,
} from "../paraglide/runtime.js";

/** Where the person's choice of language is kept. */
export const LANGUAGE_KEY = "house-cost-language";

/** Each language's name, in that language, as the language menu offers it. */
export const LANGUAGE_NAMES: Record<Locale, string> = { en: "English", "pt-PT": "Português" };

/** How each language writes dates and numbers: English with the day first and a 24-hour clock. */
const INTL: Record<Locale, string> = { en: "en-GB", "pt-PT": "pt-PT" };

/** The browser's storage, or undefined where reading it is refused (a private window, say). */
export function browserStorage(): Storage | undefined {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

/**
 * The first language the interface has among `wanted`: by its whole tag, or by its first part, so
 * "pt" and "pt-BR" find the Portuguese there is.
 */
export function match(wanted: readonly string[], available: readonly string[] = locales): Locale | undefined {
  for (const tag of wanted) {
    const lower = tag.toLowerCase();
    const exact = available.find((locale) => locale.toLowerCase() === lower);
    if (exact) return exact as Locale;
    const first = lower.split("-")[0];
    const related = available.find((locale) => locale.toLowerCase().split("-")[0] === first);
    if (related) return related as Locale;
  }
  return undefined;
}

/** Gives Paraglide the interface's two strategies: the choice in `storage`, then the browser's. */
export function useLanguageStrategies(
  languages: () => readonly string[] = () => navigator.languages ?? [],
  storage: () => Storage | undefined = browserStorage,
): void {
  defineCustomClientStrategy("custom-choice", {
    getLocale: () => chosenLanguage(storage()) ?? undefined,
    setLocale: () => {},
  });
  defineCustomClientStrategy("custom-browser", {
    getLocale: () => match(languages()),
    setLocale: () => {},
  });
}

/** The person's own choice of language, or null when the interface follows the browser. */
export function chosenLanguage(storage: Storage | undefined = browserStorage()): Locale | null {
  try {
    const saved = storage?.getItem(LANGUAGE_KEY);
    return saved && (locales as readonly string[]).includes(saved) ? (saved as Locale) : null;
  } catch {
    return null;
  }
}

/**
 * Keeps a choice of language, or forgets it when `language` is null, and reloads into it:
 * Paraglide's messages are read once per page.
 */
export function chooseLanguage(
  language: Locale | null,
  reload: () => void,
  storage: Storage | undefined = browserStorage(),
): void {
  try {
    if (language) storage?.setItem(LANGUAGE_KEY, language);
    else storage?.removeItem(LANGUAGE_KEY);
  } catch {
    // Storage refused: the interface stays in the language it is in.
    return;
  }
  reload();
}

/**
 * Settles the language for as long as the page is open, and returns it. Paraglide asks its
 * strategies again on every message, so without this a choice made in another tab would change
 * this page's words while `<html lang>` stayed as it was.
 */
export function settleLanguage(): Locale {
  const language = getLocale();
  overwriteGetLocale(() => language);
  document.documentElement.lang = language;
  return language;
}

/** The locale Intl formats dates and numbers in, for the interface's language. */
export function intlLocale(language: Locale = getLocale()): string {
  return INTL[language] ?? INTL[baseLocale];
}
