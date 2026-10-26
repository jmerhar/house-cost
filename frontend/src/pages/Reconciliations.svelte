<script lang="ts">
  import Pencil from "@lucide/svelte/icons/pencil";
  import Plus from "@lucide/svelte/icons/plus";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import { onMount } from "svelte";
  import type { Reconciliation, ReconciliationIn } from "../lib/api";
  import { useApp } from "../lib/context";
  import { reveal } from "../lib/reveal";
  import { errorMessage } from "../lib/errors";
  import { day, euros, parsePercent, percentInput } from "../lib/format";
  import { m } from "../paraglide/messages.js";

  const app = useApp();
  let reconciliations = $state<Reconciliation[]>([]);
  let loaded = $state(false);
  let error = $state("");

  /** The draft being edited: null for a new one, and its reconciled shares as typed. */
  let open = $state(false);
  let editing = $state<Reconciliation | null>(null);
  let start = $state(`${new Date().getFullYear() - 1}-01-01`);
  let end = $state(`${new Date().getFullYear() - 1}-12-31`);
  let note = $state("");
  let shares = $state<Record<string, string>>({});

  const key = (categoryId: number, householdId: number) => `${categoryId}:${householdId}`;

  async function load(): Promise<void> {
    try {
      reconciliations = await app.api.reconciliations();
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      loaded = true;
    }
  }

  onMount(() => {
    load();
  });

  function edit(reconciliation: Reconciliation | null): void {
    editing = reconciliation;
    start = reconciliation?.period_start ?? start;
    end = reconciliation?.period_end ?? end;
    note = reconciliation?.note ?? "";
    shares = Object.fromEntries(
      (reconciliation?.shares ?? []).map((s) => [key(s.category_id, s.household_id), percentInput(s.basis_points)]),
    );
    open = true;
    reveal("#reconciliation-form");
  }

  function body(): ReconciliationIn | null {
    const result: ReconciliationIn["shares"] = [];
    for (const category of app.categories) {
      const typed = app.households.map((h) => ({ h, text: (shares[key(category.id, h.id)] ?? "").trim() }));
      if (typed.every((t) => t.text === "")) continue;
      const parsed = typed.map((t) => ({ household_id: t.h.id, basis_points: parsePercent(t.text || "0") }));
      if (parsed.some((p) => p.basis_points === null) || parsed.reduce((s, p) => s + (p.basis_points ?? 0), 0) !== 10_000) {
        error = `${category.name}: ${m.error_shares_total()}`;
        return null;
      }
      for (const p of parsed) result.push({ category_id: category.id, household_id: p.household_id, basis_points: p.basis_points as number });
    }
    return { period_start: start, period_end: end, note, shares: result };
  }

  async function save(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    error = "";
    const payload = body();
    if (!payload) return;
    try {
      editing = editing
        ? await app.api.updateReconciliation(editing.id, payload)
        : await app.api.createReconciliation(payload);
      await load();
    } catch (failure) {
      error = errorMessage(failure);
    }
  }

  async function close(reconciliation: Reconciliation): Promise<void> {
    if (!confirm(m.confirm_close_reconciliation())) return;
    try {
      await app.api.closeReconciliation(reconciliation.id);
      open = false;
      await load();
    } catch (failure) {
      error = errorMessage(failure);
    }
  }

  async function discard(reconciliation: Reconciliation): Promise<void> {
    if (!confirm(m.confirm_discard_reconciliation())) return;
    try {
      await app.api.deleteReconciliation(reconciliation.id);
      open = false;
      await load();
    } catch (failure) {
      error = errorMessage(failure);
    }
  }
</script>

<div class="heading">
  <h1>{m.reconciliations_title()}</h1>
  {#if app.isAdmin && !open}<button type="button" onclick={() => edit(null)}><Plus />{m.reconciliation_new()}</button>{/if}
</div>
<p class="muted">{m.setting_reconciliation_hint()}</p>
{#if error}<p role="alert">{error}</p>{/if}

{#if open}
  <form class="card" id="reconciliation-form" onsubmit={save}>
    <div class="grid">
      <label>{m.field_period_start()}<input type="date" bind:value={start} required /></label>
      <label>{m.field_period_end()}<input type="date" bind:value={end} min={start} required /></label>
      <label class="wide">{m.field_notes()}<input bind:value={note} maxlength="2000" /></label>
    </div>
    <h2>{m.reconciliation_shares()}</h2>
    <p class="muted">{m.reconciliation_shares_hint()}</p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">{m.field_category()}</th>
            {#each app.households as household (household.id)}<th scope="col">{household.name} (%)</th>{/each}
          </tr>
        </thead>
        <tbody>
          {#each app.categories as category (category.id)}
            <tr>
              <th scope="row">{category.name}</th>
              {#each app.households as household (household.id)}
                <td>
                  <input
                    bind:value={shares[key(category.id, household.id)]}
                    inputmode="decimal"
                    aria-label={`${category.name} · ${household.name}`}
                  />
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <div class="actions">
      <button type="submit">{m.save()}</button>
      <button type="button" class="secondary" onclick={() => (open = false)}>{m.cancel()}</button>
      {#if editing}
        <button type="button" class="danger" onclick={() => editing && discard(editing)}><Trash2 />{m.delete()}</button>
      {/if}
    </div>
  </form>
{/if}

{#if !loaded}
  <p>{m.loading()}</p>
{:else if reconciliations.length === 0}
  <p>{m.reconciliations_empty()}</p>
{:else}
  {#each reconciliations as reconciliation (reconciliation.id)}
    <article class="card">
      <div class="heading">
        <h2>{day(reconciliation.period_start)} – {day(reconciliation.period_end)}</h2>
        <small class="tag">{reconciliation.status === "closed" ? m.status_closed() : m.status_draft()}</small>
      </div>
      {#if reconciliation.note}<p>{reconciliation.note}</p>{/if}
      <p class="muted">{m.reconciliation_bills({ count: reconciliation.bill_count })}</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{m.field_household()}</th>
              <th scope="col" class="num">{m.col_charged()}</th>
              <th scope="col" class="num">{m.col_reconciled()}</th>
              <th scope="col" class="num">{m.col_adjustment()}</th>
            </tr>
          </thead>
          <tbody>
            {#each reconciliation.lines as line (line.household_id)}
              <tr>
                <th scope="row">{app.household(line.household_id)}</th>
                <td class="num">{euros(line.charged_cents)}</td>
                <td class="num">{euros(line.reconciled_cents)}</td>
                <td class="num">{euros(line.adjustment_cents)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      {#if app.isAdmin && reconciliation.status === "draft"}
        <div class="actions">
          <button type="button" class="secondary" onclick={() => edit(reconciliation)}><Pencil />{m.edit()}</button>
          <button type="button" class="danger" onclick={() => close(reconciliation)}>{m.reconciliation_close()}</button>
        </div>
      {/if}
    </article>
  {/each}
{/if}
