// The interface: built into dist/, which the API serves beside /api. The shared preset sends /api
// to the API, on its default port or at VITE_API_TARGET (the dev stack's container name), and sets
// the browsers a build targets and the licences file.
import { paraglideVitePlugin } from "@inlang/paraglide-js";
import { app } from "@jmerhar/frontend-config/vite";
import { test } from "@jmerhar/frontend-config/vitest";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { svelteTesting } from "@testing-library/svelte/vite";
import { mergeConfig } from "vite";
import { defineConfig } from "vitest/config";
import { paraglideOptions } from "./build/paraglide.ts";

export default defineConfig(
  mergeConfig(app(), {
    // paraglideVitePlugin compiles messages/ into src/paraglide before each build and test run;
    // svelteTesting resolves Svelte's browser build under Vitest and cleans up after each test.
    plugins: [paraglideVitePlugin(paraglideOptions), svelte(), svelteTesting()],
    test: test({
      include: ["src/**/*.test.ts"],
      setupFiles: ["src/test-setup.ts"],
      coverage: {
        include: ["src/**/*.{ts,svelte}"],
        exclude: [
          "src/test-setup.ts",
          "src/main.ts",
          "src/lib/api-types.ts",
          "src/testing.ts",
          "src/paraglide/**",
        ],
      },
    }),
  }),
);
