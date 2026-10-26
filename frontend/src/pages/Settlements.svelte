<script lang="ts">
  import Paperclip from "@lucide/svelte/icons/paperclip";
  import Pencil from "@lucide/svelte/icons/pencil";
  import Plus from "@lucide/svelte/icons/plus";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import { onMount } from "svelte";
  import type { Attachment, Settlement } from "../lib/api";
  import { useApp } from "../lib/context";
  import { reveal } from "../lib/reveal";
  import { errorMessage } from "../lib/errors";
  import { amountInput, day, euros, parseAmount, today } from "../lib/format";
  import { m } from "../paraglide/messages.js";

  const app = useApp();
  let settlements = $state<Settlement[]>([]);
  let loaded = $state(false);
  let error = $state("");

  /** The form: open for a new transfer (editing null) or for one being corrected. */
  let open = $state(false);
  let editing = $state<Settlement | null>(null);
  let date = $state(today());
  let fromId = $state("");
  let toId = $state("");
  let amount = $state("");
  let note = $state("");
  let busy = $state(false);

  async function load(): Promise<void> {
    try {
      settlements = await app.api.settlements();
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      loaded = true;
    }
  }

  function start(from = "", to = "", cents: number | null = null): void {
    editing = null;
    date = today();
    fromId = from || String(app.me?.household_id ?? "");
    toId = to;
    amount = cents === null ? "" : amountInput(cents);
    note = "";
    open = true;
  }

  function edit(settlement: Settlement): void {
    editing = settlement;
    date = settlement.date;
    fromId = String(settlement.from_id);
    toId = String(settlement.to_id);
    amount = amountInput(settlement.amount_cents);
    note = settlement.note;
    open = true;
    reveal("#settlement-form");
  }

  onMount(() => {
    load();
    // Arriving from a suggested transfer on the balances page, with the form filled in.
    const query = new URLSearchParams(location.search);
    if (query.has("from")) start(query.get("from") ?? "", query.get("to") ?? "", Number(query.get("amount")) || null);
  });

  async function save(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    error = "";
    const cents = parseAmount(amount);
    if (cents === null || cents <= 0) {
      error = m.error_amount();
      return;
    }
    busy = true;
    const body = { date, from_id: Number(fromId), to_id: Number(toId), amount_cents: cents, note };
    try {
      if (editing) await app.api.updateSettlement(editing.id, body);
      else await app.api.createSettlement(body);
      open = false;
      await load();
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      busy = false;
    }
  }

  async function remove(settlement: Settlement): Promise<void> {
    if (!confirm(m.confirm_delete_settlement())) return;
    try {
      await app.api.deleteSettlement(settlement.id);
      open = false;
      await load();
    } catch (failure) {
      error = errorMessage(failure);
    }
  }

  async function attach(settlement: Settlement, event: Event): Promise<void> {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    try {
      const added: Attachment = await app.api.attach(file, { settlement_id: settlement.id });
      settlements = settlements.map((s) => (s.id === settlement.id ? { ...s, attachments: [...s.attachments, added] } : s));
    } catch (failure) {
      error = errorMessage(failure);
    }
    input.value = "";
  }
</script>

<div class="heading">
  <h1>{m.settlements_title()}</h1>
  {#if !open}<button type="button" onclick={() => start()}><Plus />{m.settlement_new()}</button>{/if}
</div>

{#if open}
  <form class="card" id="settlement-form" onsubmit={save}>
    <h2>{editing ? m.settlement_edit() : m.settlement_new()}</h2>
    <div class="grid">
      <label>{m.field_date()}<input type="date" bind:value={date} required /></label>
      <label>
        {m.field_amount()}<input bind:value={amount} inputmode="decimal" required placeholder={amountInput(0)} />
      </label>
      <label>
        {m.field_from()}
        <select bind:value={fromId} required>
          {#each app.households as household (household.id)}
            <option value={String(household.id)}>{household.name}</option>
          {/each}
        </select>
      </label>
      <label>
        {m.field_to()}
        <select bind:value={toId} required>
          <option value="" disabled>—</option>
          {#each app.households.filter((h) => String(h.id) !== fromId) as household (household.id)}
            <option value={String(household.id)}>{household.name}</option>
          {/each}
        </select>
      </label>
      <label class="wide">{m.field_notes()}<input bind:value={note} maxlength="2000" /></label>
    </div>
    {#if error}<p role="alert">{error}</p>{/if}
    <div class="actions">
      <button type="submit" disabled={busy}>{busy ? m.saving() : m.save()}</button>
      <button type="button" class="secondary" onclick={() => (open = false)}>{m.cancel()}</button>
      {#if editing}
        <button type="button" class="danger" onclick={() => editing && remove(editing)}><Trash2 />{m.delete()}</button>
      {/if}
    </div>
  </form>
{:else if error}
  <p role="alert">{error}</p>
{/if}

{#if !loaded}
  <p>{m.loading()}</p>
{:else if settlements.length === 0}
  <p>{m.settlements_empty()}</p>
{:else}
  <ul class="list">
    {#each settlements as settlement (settlement.id)}
      <li>
        <span class="when">{day(settlement.date)}</span>
        <span class="what">
          <strong>{m.settlement_line({ from: app.household(settlement.from_id), to: app.household(settlement.to_id) })}</strong>
          {#if settlement.note}<small>{settlement.note}</small>{/if}
          {#each settlement.attachments as attachment (attachment.id)}
            <small><a href={app.api.attachmentUrl(attachment.id)} target="_blank" rel="noopener">{attachment.filename}</a></small>
          {/each}
        </span>
        <span class="amount">{euros(settlement.amount_cents)}</span>
        <span class="row-actions">
          <button type="button" class="link" onclick={() => edit(settlement)}><Pencil />{m.edit()}</button>
          <label class="link">
            <Paperclip />{m.files_add()}
            <input type="file" accept="application/pdf,image/*" class="file-input" onchange={(event) => attach(settlement, event)} />
          </label>
        </span>
      </li>
    {/each}
  </ul>
{/if}
