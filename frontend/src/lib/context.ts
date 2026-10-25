/** The app's shared state, handed to every view through Svelte's context. */

import { getContext, setContext } from "svelte";
import type { AppState } from "./state.svelte";

const KEY = Symbol("app");

/** Make ``state`` the app's state for this component and everything inside it. */
export function provideApp(state: AppState): void {
  setContext(KEY, state);
}

/** The app's state, as provided by an enclosing component. */
export function useApp(): AppState {
  return getContext<AppState>(KEY);
}

/** The context a component tree is rendered with when ``state`` is the app's state. */
export function contextFor(state: AppState): Map<symbol, AppState> {
  return new Map([[KEY, state]]);
}
