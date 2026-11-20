import { base, node } from "@jmerhar/frontend-config/eslint";
import { svelte } from "@jmerhar/frontend-config/eslint/svelte";

// The shared presets; src/paraglide is compiled from messages/ on every build and test run.
export default [...base({ ignores: ["src/paraglide", "public"] }), ...svelte(), node(["build/**/*.ts"])];
