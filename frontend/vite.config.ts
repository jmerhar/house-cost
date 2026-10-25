// The interface: built into dist/, which the API serves beside /api. The dev server hands /api to
// the API, on its default port or at VITE_API_TARGET (the dev stack's container name).
import { paraglideVitePlugin } from "@inlang/paraglide-js";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { svelteTesting } from "@testing-library/svelte/vite";
import { defineConfig } from "vitest/config";
import { paraglideOptions } from "./build/paraglide.ts";

// The one Node global read here, declared rather than pulling in all of @types/node.
declare const process: { env: Record<string, string | undefined> };
const api = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  // paraglideVitePlugin compiles messages/ into src/paraglide before each build and test run;
  // svelteTesting resolves Svelte's browser build under Vitest and cleans up after each test.
  plugins: [paraglideVitePlugin(paraglideOptions), svelte(), svelteTesting()],
  server: { proxy: { "/api": api } },
  build: {
    target: ["chrome109", "edge109", "firefox115", "safari16", "ios16"],
    // The licences of everything bundled, which theirs ask to travel with it.
    license: { fileName: "licenses.md" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test-setup.ts"],
    include: ["src/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,svelte}"],
      exclude: [
        "src/**/*.test.ts",
        "src/test-setup.ts",
        "src/main.ts",
        "src/lib/api-types.ts",
        "src/paraglide/**",
      ],
      // json-summary is the istanbul file coverage.toml's shared tooling reads; lcov is Codecov's.
      reporter: ["text", "json-summary", "json", "lcov", ["html", { subdir: "html" }]],
      reportsDirectory: "coverage",
    },
  },
});
