<script lang="ts">
  import { onMount } from "svelte";
  import type { Category, Household, Person, Rule } from "../lib/api";
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { day, parsePercent, percent, today } from "../lib/format";
  import { LANGUAGE_NAMES } from "../lib/language";
  import { m } from "../paraglide/messages.js";
  import { locales, type Locale } from "../paraglide/runtime.js";

  const app = useApp();
  let people = $state<Person[]>([]);
  let rules = $state<Rule[]>([]);
  let reconciliation = $state(app.me?.reconciliation_enabled ?? false);
  let error = $state("");

  async function load(): Promise<void> {
    try {
      [people, rules] = await Promise.all([app.api.people(), app.api.rules()]);
      await app.refresh();
    } catch (failure) {
      error = errorMessage(failure);
    }
  }

  onMount(() => {
    load();
  });

  /** Run a change, then reload what it may have changed; any refusal is shown. */
  async function attempt(change: () => Promise<unknown>): Promise<boolean> {
    error = "";
    try {
      await change();
      await load();
      return true;
    } catch (failure) {
      error = errorMessage(failure);
      return false;
    }
  }

  // --- Households ---
  let householdName = $state("");
  async function addHousehold(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const position = Math.max(-1, ...app.households.map((h) => h.position)) + 1;
    if (await attempt(() => app.api.createHousehold({ name: householdName, position, active: true }))) householdName = "";
  }
  function saveHousehold(household: Household, changes: Partial<Household>): Promise<boolean> {
    return attempt(() =>
      app.api.updateHousehold(household.id, {
        name: household.name,
        position: household.position,
        active: household.active,
        ...changes,
      }),
    );
  }
  function renameHousehold(household: Household): void {
    const name = prompt(m.field_name(), household.name);
    if (name && name !== household.name) saveHousehold(household, { name });
  }

  // --- People ---
  let personForm = $state<{ id: number | null; name: string; login: string; role: "admin" | "member"; language: string; householdId: string; active: boolean; password: string } | null>(null);
  function newPerson(): void {
    personForm = { id: null, name: "", login: "", role: "member", language: "", householdId: String(app.households[0]?.id ?? ""), active: true, password: "" };
  }
  function editPerson(person: Person): void {
    personForm = {
      id: person.id,
      name: person.name,
      login: person.login,
      role: person.role,
      language: person.language ?? "",
      householdId: String(person.household_id),
      active: person.active,
      password: "",
    };
  }
  async function savePerson(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const form = personForm;
    if (!form) return;
    const fields = {
      name: form.name,
      login: form.login,
      role: form.role,
      language: (form.language || null) as Locale | null,
      household_id: Number(form.householdId),
    };
    const ok = await attempt(() =>
      form.id === null
        ? app.api.createPerson({ ...fields, password: form.password })
        : app.api.updatePerson(form.id, { ...fields, active: form.active, password: form.password || null }),
    );
    if (ok) personForm = null;
  }

  // --- Categories and rules ---
  let categoryName = $state("");
  async function addCategory(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (await attempt(() => app.api.createCategory({ name: categoryName, description: "", active: true }))) categoryName = "";
  }
  function toggleCategory(category: Category): void {
    attempt(() =>
      app.api.updateCategory(category.id, { name: category.name, description: category.description, active: !category.active }),
    );
  }

  let ruleFor = $state<number | null>(null);
  let ruleFrom = $state(today());
  let ruleNote = $state("");
  let ruleShares = $state<Record<number, string>>({});
  function newRule(category: Category): void {
    ruleFor = category.id;
    ruleFrom = today();
    ruleNote = "";
    // Start from the category's current split, which a change usually adjusts.
    const latest = rules.filter((rule) => rule.category_id === category.id).at(-1);
    ruleShares = Object.fromEntries(
      app.households.map((h) => [h.id, String((latest?.shares.find((s) => s.household_id === h.id)?.basis_points ?? 0) / 100)]),
    );
  }
  const ruleTotal = $derived(Object.values(ruleShares).reduce((sum, text) => sum + (parsePercent(text) ?? 0), 0));
  async function saveRule(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (ruleFor === null) return;
    const shares = app.households.map((h) => ({ household_id: h.id, basis_points: parsePercent(ruleShares[h.id] ?? "0") }));
    if (shares.some((s) => s.basis_points === null) || ruleTotal !== 10_000) {
      error = m.error_shares_total();
      return;
    }
    const category = ruleFor;
    const ok = await attempt(() =>
      app.api.createRule({
        category_id: category,
        effective_from: ruleFrom,
        note: ruleNote,
        shares: shares.map((s) => ({ household_id: s.household_id, basis_points: s.basis_points as number })),
      }),
    );
    if (ok) ruleFor = null;
  }
  function deleteRule(rule: Rule): void {
    if (confirm(m.confirm_delete_rule())) attempt(() => app.api.deleteRule(rule.id));
  }
  function split(rule: Rule): string {
    return rule.shares.map((share) => `${app.household(share.household_id)} ${percent(share.basis_points)}`).join(" · ");
  }

  // --- Settings ---
  async function toggleReconciliation(): Promise<void> {
    const wanted = !reconciliation;
    if (await attempt(() => app.api.updateSettings({ reconciliation_enabled: wanted }))) {
      reconciliation = wanted;
      if (app.me) app.me = { ...app.me, reconciliation_enabled: wanted };
    }
  }
</script>

<h1>{m.admin_title()}</h1>
{#if error}<p role="alert">{error}</p>{/if}

<section>
  <h2>{m.households_title()}</h2>
  <ul class="list">
    {#each app.households as household, index (household.id)}
      <li>
        <span class="what"><strong>{household.name}</strong>{#if !household.active}<small>{m.inactive()}</small>{/if}</span>
        <span class="row-actions">
          <button type="button" class="link" onclick={() => renameHousehold(household)}>{m.edit()}</button>
          {#if index > 0}
            <button
              type="button"
              class="link"
              aria-label="↑ {household.name}"
              onclick={() => saveHousehold(household, { position: app.households[index - 1].position - 1 })}>↑</button
            >
          {/if}
          <button type="button" class="link" onclick={() => saveHousehold(household, { active: !household.active })}>
            {household.active ? m.inactive() : m.active()}
          </button>
        </span>
      </li>
    {/each}
  </ul>
  <form class="inline" onsubmit={addHousehold}>
    <input bind:value={householdName} required maxlength="100" aria-label={m.household_add()} placeholder={m.household_add()} />
    <button type="submit">{m.add()}</button>
  </form>
</section>

<section>
  <h2>{m.people_title()}</h2>
  <ul class="list">
    {#each people as person (person.id)}
      <li>
        <span class="what">
          <strong>{person.name}</strong>
          <small>
            {person.login} · {app.household(person.household_id)} · {person.role === "admin" ? m.role_admin() : m.role_member()}
            {#if !person.active}· {m.inactive()}{/if}
          </small>
        </span>
        <button type="button" class="link" onclick={() => editPerson(person)}>{m.edit()}</button>
      </li>
    {/each}
  </ul>
  {#if personForm}
    <form class="card" onsubmit={savePerson}>
      <div class="grid">
        <label>{m.field_name()}<input bind:value={personForm.name} required maxlength="100" /></label>
        <label>{m.field_login()}<input bind:value={personForm.login} required maxlength="100" autocapitalize="none" /></label>
        <label>
          {m.field_household()}
          <select bind:value={personForm.householdId}>
            {#each app.households as household (household.id)}<option value={String(household.id)}>{household.name}</option>{/each}
          </select>
        </label>
        <label>
          {m.field_role()}
          <select bind:value={personForm.role}>
            <option value="member">{m.role_member()}</option>
            <option value="admin">{m.role_admin()}</option>
          </select>
        </label>
        <label>
          {m.language_label()}
          <select bind:value={personForm.language}>
            <option value="">{m.language_browser()}</option>
            {#each locales as locale (locale)}<option value={locale}>{LANGUAGE_NAMES[locale]}</option>{/each}
          </select>
        </label>
        <label>
          {personForm.id === null ? m.field_password() : m.field_reset_password()}
          <input type="password" bind:value={personForm.password} minlength="10" required={personForm.id === null} autocomplete="new-password" />
        </label>
        {#if personForm.id !== null}
          <label class="check"><input type="checkbox" bind:checked={personForm.active} /> {m.active()}</label>
        {/if}
      </div>
      <div class="actions">
        <button type="submit">{m.save()}</button>
        <button type="button" class="secondary" onclick={() => (personForm = null)}>{m.cancel()}</button>
      </div>
    </form>
  {:else}
    <button type="button" class="secondary" onclick={newPerson}>{m.person_add()}</button>
  {/if}
</section>

<section>
  <h2>{m.categories_title()}</h2>
  <p class="muted">{m.rule_hint()}</p>
  {#each app.categories as category (category.id)}
    {@const own = rules.filter((rule) => rule.category_id === category.id)}
    <article class="card">
      <div class="heading">
        <h3>{category.name}{#if !category.active} <small>({m.inactive()})</small>{/if}</h3>
        <span class="row-actions">
          <button type="button" class="link" onclick={() => newRule(category)}>{m.rule_add()}</button>
          <button type="button" class="link" onclick={() => toggleCategory(category)}>
            {category.active ? m.inactive() : m.active()}
          </button>
        </span>
      </div>
      {#if own.length === 0}<p class="muted">{m.category_no_rule()}</p>{/if}
      <ul class="list">
        {#each own as rule (rule.id)}
          <li>
            <span class="what">
              <strong>{m.rule_since({ date: day(rule.effective_from) })}</strong>
              <small>{split(rule)}</small>
              {#if rule.note}<small>{rule.note}</small>{/if}
            </span>
            {#if rule.in_use}
              <small class="tag">{m.rule_in_use()}</small>
            {:else}
              <button type="button" class="link" onclick={() => deleteRule(rule)}>{m.rule_delete()}</button>
            {/if}
          </li>
        {/each}
      </ul>
      {#if ruleFor === category.id}
        <form onsubmit={saveRule}>
          <div class="grid">
            <label>{m.field_effective_from()}<input type="date" bind:value={ruleFrom} required /></label>
            {#each app.households as household (household.id)}
              <label>
                {household.name} (%)
                <input bind:value={ruleShares[household.id]} inputmode="decimal" required />
              </label>
            {/each}
            <label class="wide">{m.field_rule_note()}<input bind:value={ruleNote} maxlength="2000" /></label>
          </div>
          <p class:problem={ruleTotal !== 10_000}>{m.rule_total({ percent: percent(ruleTotal) })}</p>
          <div class="actions">
            <button type="submit">{m.save()}</button>
            <button type="button" class="secondary" onclick={() => (ruleFor = null)}>{m.cancel()}</button>
          </div>
        </form>
      {/if}
    </article>
  {/each}
  <form class="inline" onsubmit={addCategory}>
    <input bind:value={categoryName} required maxlength="100" aria-label={m.category_add()} placeholder={m.category_add()} />
    <button type="submit">{m.add()}</button>
  </form>
</section>

<section>
  <h2>{m.settings_title()}</h2>
  <label class="check">
    <input type="checkbox" checked={reconciliation} onchange={toggleReconciliation} />
    {m.setting_reconciliation()}
  </label>
  <p class="muted">{m.setting_reconciliation_hint()}</p>
</section>
