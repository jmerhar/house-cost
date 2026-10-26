/**
 * What every view needs: the person logged in, and the households and categories bills refer to.
 * Loaded once after logging in, and again whenever an admin changes them.
 */

import type { Api, Category, Household, Me } from "./api";
import { browserAuthenticator, type Authenticator } from "./passkeys";

export class AppState {
  me = $state<Me | null>(null);
  households = $state<Household[]>([]);
  categories = $state<Category[]>([]);

  constructor(
    readonly api: Api,
    readonly authenticator: Authenticator = browserAuthenticator,
  ) {}

  /** Load the households and categories, after logging in or after an admin changed them. */
  async refresh(): Promise<void> {
    const [households, categories] = await Promise.all([this.api.households(), this.api.categories()]);
    this.households = households;
    this.categories = categories;
  }

  /** A household's name, by id. */
  household(id: number): string {
    return this.households.find((household) => household.id === id)?.name ?? `#${id}`;
  }

  /** A category's name, by id. */
  category(id: number): string {
    return this.categories.find((category) => category.id === id)?.name ?? `#${id}`;
  }

  get isAdmin(): boolean {
    return this.me?.role === "admin";
  }
}
