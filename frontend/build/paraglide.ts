/**
 * How Paraglide compiles the interface's messages, shared by the Vite plugin (builds, the dev
 * server and Vitest) and by compile-messages.ts, which writes them for svelte-check.
 *
 * The language is the person's own choice, else the first of the browser's languages the
 * interface has, else English: the first two are the interface's own strategies, defined in
 * src/lib/language.ts.
 */
export const paraglideOptions = {
  project: "./project.inlang",
  outdir: "./src/paraglide",
  strategy: ["custom-choice", "custom-browser", "baseLocale"] as ("custom-choice" | "custom-browser" | "baseLocale")[],
};
