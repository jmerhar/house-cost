import { afterEach, describe, expect, it, vi } from "vitest";
import {
  LANGUAGE_KEY,
  browserStorage,
  chooseLanguage,
  chosenLanguage,
  intlLocale,
  match,
  settleLanguage,
  useLanguageStrategies,
} from "./language";
import { getLocale } from "../paraglide/runtime.js";

/** A Storage whose every call throws, as a browser refusing site data does. */
const refusing = {
  getItem: () => {
    throw new Error("refused");
  },
  setItem: () => {
    throw new Error("refused");
  },
  removeItem: () => {
    throw new Error("refused");
  },
} as unknown as Storage;

afterEach(() => {
  // Mocks first: one test makes reading localStorage itself throw.
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("match", () => {
  it("finds a language by its whole tag", () => {
    expect(match(["pt-PT"])).toBe("pt-PT");
  });

  it("finds a language by its first part", () => {
    expect(match(["pt-BR"])).toBe("pt-PT");
    expect(match(["PT"])).toBe("pt-PT");
  });

  it("takes the first wanted language it has", () => {
    expect(match(["de", "en-US", "pt"])).toBe("en");
  });

  it("finds nothing when it has none of them", () => {
    expect(match(["de", "fr"])).toBeUndefined();
  });
});

describe("chosenLanguage", () => {
  it("reads a choice that was kept", () => {
    localStorage.setItem(LANGUAGE_KEY, "pt-PT");
    expect(chosenLanguage()).toBe("pt-PT");
  });

  it("ignores a stored value that is not a language it has", () => {
    localStorage.setItem(LANGUAGE_KEY, "klingon");
    expect(chosenLanguage()).toBeNull();
  });

  it("is null when storage refuses or is missing", () => {
    expect(chosenLanguage(refusing)).toBeNull();
    expect(chosenLanguage(undefined)).toBeNull();
  });
});

describe("chooseLanguage", () => {
  it("keeps a choice and reloads into it", () => {
    const reload = vi.fn();
    chooseLanguage("pt-PT", reload);
    expect(localStorage.getItem(LANGUAGE_KEY)).toBe("pt-PT");
    expect(reload).toHaveBeenCalledOnce();
  });

  it("forgets the choice to follow the browser again", () => {
    localStorage.setItem(LANGUAGE_KEY, "pt-PT");
    const reload = vi.fn();
    chooseLanguage(null, reload);
    expect(localStorage.getItem(LANGUAGE_KEY)).toBeNull();
    expect(reload).toHaveBeenCalledOnce();
  });

  it("stays put when storage refuses", () => {
    const reload = vi.fn();
    chooseLanguage("pt-PT", reload, refusing);
    expect(reload).not.toHaveBeenCalled();
  });
});

describe("browserStorage", () => {
  it("is the page's localStorage", () => {
    expect(browserStorage()).toBe(window.localStorage);
  });

  it("is undefined when reading it is refused", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expect(browserStorage()).toBeUndefined();
  });
});

describe("the strategies", () => {
  afterEach(() => useLanguageStrategies());

  it("prefer the person's choice over the browser's languages", () => {
    localStorage.setItem(LANGUAGE_KEY, "en");
    useLanguageStrategies(() => ["pt-PT"]);
    expect(getLocale()).toBe("en");
  });

  it("follow the browser when nothing was chosen", () => {
    useLanguageStrategies(() => ["pt-BR", "en"]);
    expect(getLocale()).toBe("pt-PT");
  });

  it("fall back to English", () => {
    useLanguageStrategies(() => ["de"]);
    expect(getLocale()).toBe("en");
  });
});

describe("settleLanguage", () => {
  it("fixes the language for the page and labels the document with it", () => {
    useLanguageStrategies(() => ["pt-PT"]);
    expect(settleLanguage()).toBe("pt-PT");
    useLanguageStrategies(() => ["en"]);
    expect(getLocale()).toBe("pt-PT");
    expect(document.documentElement.lang).toBe("pt-PT");
  });
});

describe("intlLocale", () => {
  it("writes English dates day first", () => {
    expect(intlLocale("en")).toBe("en-GB");
    expect(intlLocale("pt-PT")).toBe("pt-PT");
  });
});
