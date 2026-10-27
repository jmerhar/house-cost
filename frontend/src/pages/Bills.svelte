<script lang="ts">
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import Plus from "@lucide/svelte/icons/plus";
  import Upload from "@lucide/svelte/icons/upload";
  import { onMount } from "svelte";
  import type { Bill } from "../lib/api";
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { holdDraft } from "../lib/draft";
  import { day, euros } from "../lib/format";
  import { navigate } from "../lib/router.svelte";
  import { m } from "../paraglide/messages.js";

  const PAGE = 50;
  const app = useApp();

  let bills = $state<Bill[]>([]);
  let total = $state(0);
  let loaded = $state(false);
  let error = $state("");
  let q = $state("");
  let year = $state("");
  let categoryId = $state("");
  let paidById = $state("");
  let years = $state<number[]>([]);

  const filtered = $derived(Boolean(q || year || categoryId || paidById));

  async function load(more = false): Promise<void> {
    error = "";
    try {
      const page = await app.api.bills({
        q,
        year,
        category_id: categoryId,
        paid_by_id: paidById,
        limit: PAGE,
        offset: more ? bills.length : 0,
      });
      bills = more ? [...bills, ...page.items] : page.items;
      total = page.total;
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      loaded = true;
    }
  }

  let timer: ReturnType<typeof setTimeout> | undefined;
  function search(): void {
    clearTimeout(timer);
    timer = setTimeout(() => load(), 250);
  }

  async function loadYears(): Promise<void> {
    try {
      years = (await app.api.summary()).years;
    } catch {
      // The year filter just stays short; the list itself reports failures.
    }
  }

  onMount(() => {
    load();
    loadYears();
    return () => clearTimeout(timer);
  });

  let reading = $state(false);

  /** Read a bill's file and open the bill form with what it says, to be checked. */
  async function readFile(event: Event): Promise<void> {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    reading = true;
    error = "";
    try {
      holdDraft({ proposal: await app.api.readBill(file), file });
      navigate("/bills/new");
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      reading = false;
    }
  }

  function categories(bill: Bill): string {
    return [...new Set(bill.lines.map((line) => app.category(line.category_id)))].join(", ");
  }
</script>

<div class="heading">
  <h1>{m.bills_title()}</h1>
  <span class="row-actions">
    <label class="button secondary" aria-busy={reading}>
      <Upload />{reading ? m.reading_file() : m.bill_read()}
      <input type="file" accept="application/pdf,image/*" class="file-input" disabled={reading} onchange={readFile} />
    </label>
    <a class="button" href="/bills/new"><Plus />{m.bill_new()}</a>
  </span>
</div>

<div class="filters">
  <label class="grow">
    {m.search_label()}
    <input type="search" bind:value={q} oninput={search} placeholder={m.search_placeholder()} />
  </label>
  <label>
    {m.filter_year()}
    <select bind:value={year} onchange={() => load()}>
      <option value="">{m.filter_all_years()}</option>
      {#each years as y (y)}<option value={String(y)}>{y}</option>{/each}
    </select>
  </label>
  <label>
    {m.filter_category()}
    <select bind:value={categoryId} onchange={() => load()}>
      <option value="">{m.filter_all_categories()}</option>
      {#each app.categories as category (category.id)}
        <option value={String(category.id)}>{category.name}</option>
      {/each}
    </select>
  </label>
  <label>
    {m.filter_paid_by()}
    <select bind:value={paidById} onchange={() => load()}>
      <option value="">{m.filter_anyone()}</option>
      {#each app.households as household (household.id)}
        <option value={String(household.id)}>{household.name}</option>
      {/each}
    </select>
  </label>
</div>

{#if error}
  <p role="alert">{error}</p>
{:else if !loaded}
  <p>{m.loading()}</p>
{:else if bills.length === 0}
  <p>{filtered ? m.bills_none_match() : m.bills_empty()}</p>
{:else}
  <p class="muted">{m.bill_count({ count: total })}</p>
  <ul class="list">
    {#each bills as bill (bill.id)}
      <li>
        <a class="row" href={`/bills/${bill.id}`}>
          <span class="when">{day(bill.date)}</span>
          <span class="what">
            <strong>{bill.supplier || bill.description || categories(bill)}</strong>
            <small>{categories(bill)} · {m.bill_paid_by({ name: app.household(bill.paid_by_id) })}</small>
            {#if bill.notes}<small class="notes">{bill.notes}</small>{/if}
          </span>
          <span class="amount">
            {euros(bill.total_cents)}
            {#if bill.locked}<small class="tag">{m.bill_locked()}</small>{/if}
          </span>
        </a>
      </li>
    {/each}
  </ul>
  {#if bills.length < total}
    <button type="button" class="secondary" onclick={() => load(true)}><ChevronDown />{m.show_more()}</button>
  {/if}
{/if}
