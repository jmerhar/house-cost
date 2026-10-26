<script lang="ts">
  import { onMount } from "svelte";
  import type { Attachment, Bill, BillIn, Service, Supplier } from "../lib/api";
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { amountInput, euros, fileSize, parseAmount, today } from "../lib/format";
  import { navigate } from "../lib/router.svelte";
  import { m } from "../paraglide/messages.js";

  let { id }: { id?: number } = $props();
  const app = useApp();

  type LineDraft = { key: number; id: number | null; description: string; categoryId: string; amount: string };
  type Preview = { text: string; problem: boolean };

  let nextKey = 0;
  const blankLine = (): LineDraft => ({ key: nextKey++, id: null, description: "", categoryId: "", amount: "" });

  // The page is remounted for each bill (App.svelte keys it on the id), so reading the id once is
  // all it needs.
  // svelte-ignore state_referenced_locally
  let loaded = $state(id === undefined);
  let locked = $state(false);
  let date = $state(today());
  let supplier = $state("");
  let description = $state("");
  let invoice = $state("");
  let periodStart = $state("");
  let periodEnd = $state("");
  let due = $state("");
  let paidBy = $state(String(app.me?.household_id ?? ""));
  let serviceId = $state("");
  let services = $state<Service[]>([]);
  let suppliers = $state<Supplier[]>([]);
  let notes = $state("");
  let lines = $state<LineDraft[]>([blankLine()]);
  let attachments = $state<Attachment[]>([]);
  let previews = $state<Record<number, Preview>>({});
  let busy = $state(false);
  let error = $state("");

  const activeCategories = $derived(app.categories.filter((category) => category.active));
  const totalCents = $derived(lines.reduce((sum, line) => sum + (parseAmount(line.amount) ?? 0), 0));

  function fill(bill: Bill): void {
    date = bill.date;
    supplier = bill.supplier;
    description = bill.description;
    invoice = bill.invoice_number ?? "";
    periodStart = bill.period_start ?? "";
    periodEnd = bill.period_end ?? "";
    due = bill.due_date ?? "";
    paidBy = String(bill.paid_by_id);
    serviceId = bill.service_id ? String(bill.service_id) : "";
    notes = bill.notes;
    locked = bill.locked;
    attachments = bill.attachments;
    lines = bill.lines.map((line) => ({
      key: nextKey++,
      id: line.id,
      description: line.description,
      categoryId: String(line.category_id),
      amount: amountInput(line.amount_cents),
    }));
  }

  onMount(() => {
    Promise.all([app.api.services(), app.api.suppliers()]).then(
      ([loadedServices, loadedSuppliers]) => {
        services = loadedServices.filter((service) => service.active || String(service.id) === serviceId);
        suppliers = loadedSuppliers;
      },
      () => {
        // Without them the bill is entered without a service, which is allowed.
      },
    );
    if (id === undefined) return;
    app.api.bill(id).then(
      (bill) => {
        fill(bill);
        loaded = true;
      },
      (failure) => {
        error = errorMessage(failure);
        loaded = true;
      },
    );
  });

  /** Choosing a service fills in what it implies and is still empty: the supplier, and the
   * first line's category. */
  function chooseService(): void {
    const service = services.find((s) => String(s.id) === serviceId);
    if (!service) return;
    if (!supplier) supplier = suppliers.find((s) => s.id === service.supplier_id)?.name ?? "";
    if (service.default_category_id && !lines[0].categoryId) lines[0].categoryId = String(service.default_category_id);
  }

  /** Show each line's split as it would be saved, asking the API for the rule in force. */
  let previewTimer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const wanted = lines.map((line) => ({ key: line.key, categoryId: line.categoryId, cents: parseAmount(line.amount) }));
    const on = date;
    clearTimeout(previewTimer);
    previewTimer = setTimeout(async () => {
      const next: Record<number, Preview> = {};
      for (const line of wanted) {
        if (!line.categoryId || line.cents === null || !on) continue;
        try {
          const preview = await app.api.splitPreview(Number(line.categoryId), on, line.cents);
          next[line.key] = {
            text: preview.shares.map((share) => `${app.household(share.household_id)} ${euros(share.amount_cents)}`).join(" · "),
            problem: false,
          };
        } catch (failure) {
          next[line.key] = { text: errorMessage(failure), problem: true };
        }
      }
      previews = next;
    }, 300);
    return () => clearTimeout(previewTimer);
  });

  function body(): BillIn | null {
    const parsed = lines.map((line) => ({ line, cents: parseAmount(line.amount) }));
    if (parsed.some((item) => item.cents === null)) {
      error = m.error_amount();
      return null;
    }
    return {
      date,
      supplier,
      description,
      invoice_number: invoice || null,
      period_start: periodStart || null,
      period_end: periodEnd || null,
      due_date: due || null,
      paid_by_id: Number(paidBy),
      service_id: serviceId ? Number(serviceId) : null,
      notes,
      lines: parsed.map(({ line, cents }) => ({
        id: line.id,
        description: line.description,
        category_id: Number(line.categoryId),
        amount_cents: cents as number,
      })),
    };
  }

  async function save(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    error = "";
    const payload = body();
    if (!payload) return;
    busy = true;
    try {
      // A new bill opens as itself, where its files can be attached; a corrected one goes back to
      // the list.
      if (id === undefined) navigate(`/bills/${(await app.api.createBill(payload)).id}`, { replace: true });
      else {
        await app.api.updateBill(id, payload);
        navigate("/bills");
      }
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      busy = false;
    }
  }

  async function remove(): Promise<void> {
    if (id === undefined || !confirm(m.confirm_delete_bill())) return;
    try {
      await app.api.deleteBill(id);
      navigate("/bills");
    } catch (failure) {
      error = errorMessage(failure);
    }
  }

  async function attach(event: Event): Promise<void> {
    const input = event.currentTarget as HTMLInputElement;
    if (id === undefined || !input.files) return;
    error = "";
    for (const file of input.files) {
      try {
        attachments = [...attachments, await app.api.attach(file, { bill_id: id })];
      } catch (failure) {
        error = errorMessage(failure);
      }
    }
    input.value = "";
  }

  async function detach(attachment: Attachment): Promise<void> {
    if (!confirm(m.confirm_remove_file())) return;
    try {
      await app.api.deleteAttachment(attachment.id);
      attachments = attachments.filter((other) => other.id !== attachment.id);
    } catch (failure) {
      error = errorMessage(failure);
    }
  }
</script>

<a href="/bills">← {m.bills_title()}</a>
<h1>{id === undefined ? m.bill_new_title() : m.bill_edit_title()}</h1>

{#if !loaded}
  <p>{m.loading()}</p>
{:else}
  {#if locked}<p class="note">{m.error_period_closed()}</p>{/if}
  <form onsubmit={save}>
    <fieldset disabled={locked || busy}>
      <div class="grid">
        <label>{m.field_date()}<input type="date" bind:value={date} required /></label>
        <label>
          {m.field_paid_by()}
          <select bind:value={paidBy} required>
            {#each app.households as household (household.id)}
              <option value={String(household.id)}>{household.name}</option>
            {/each}
          </select>
        </label>
        <label>
          {m.field_service()} <small>({m.optional()})</small>
          <select bind:value={serviceId} onchange={chooseService}>
            <option value="">—</option>
            {#each services as service (service.id)}<option value={String(service.id)}>{service.name}</option>{/each}
          </select>
        </label>
        <label>{m.field_supplier()}<input bind:value={supplier} maxlength="200" /></label>
        <label>{m.field_invoice()}<input bind:value={invoice} maxlength="100" /></label>
        <label class="wide">{m.field_description()}<input bind:value={description} maxlength="300" /></label>
        <label>{m.field_period_from()}<input type="date" bind:value={periodStart} /></label>
        <label>{m.field_period_to()}<input type="date" bind:value={periodEnd} min={periodStart || undefined} /></label>
        <label>{m.field_due()}<input type="date" bind:value={due} /></label>
      </div>

      <h2>{m.lines_title()}</h2>
      <ol class="lines">
        {#each lines as line, index (line.key)}
          <li class="card">
            <div class="grid">
              <label>
                {m.field_category()}
                <select bind:value={line.categoryId} required>
                  <option value="" disabled>—</option>
                  {#each activeCategories as category (category.id)}
                    <option value={String(category.id)}>{category.name}</option>
                  {/each}
                  {#if line.categoryId && !activeCategories.some((c) => String(c.id) === line.categoryId)}
                    <option value={line.categoryId}>{app.category(Number(line.categoryId))}</option>
                  {/if}
                </select>
              </label>
              <label>
                {m.field_amount()}
                <input bind:value={line.amount} inputmode="decimal" required placeholder="0,00" />
              </label>
              <label class="wide">
                {m.field_line_description()} <small>({m.optional()})</small>
                <input bind:value={line.description} maxlength="300" />
              </label>
            </div>
            {#if previews[line.key]}
              <p class="split" class:problem={previews[line.key].problem}>
                {m.split_label()}: {previews[line.key].text}
              </p>
            {/if}
            {#if lines.length > 1}
              <button type="button" class="link" onclick={() => (lines = lines.filter((_, i) => i !== index))}>
                {m.line_remove()}
              </button>
            {/if}
          </li>
        {/each}
      </ol>
      <button type="button" class="secondary" onclick={() => (lines = [...lines, blankLine()])}>{m.line_add()}</button>
      <p class="total">{m.total_label()}: <strong>{euros(totalCents)}</strong></p>

      <label>{m.field_notes()}<textarea bind:value={notes} rows="3" maxlength="2000"></textarea></label>
    </fieldset>

    {#if error}<p role="alert">{error}</p>{/if}
    {#if !locked}
      <div class="actions">
        <button type="submit" disabled={busy}>{busy ? m.saving() : m.save()}</button>
        <a class="button secondary" href="/bills">{m.cancel()}</a>
        {#if id !== undefined}
          <button type="button" class="danger" onclick={remove}>{m.delete()}</button>
        {/if}
      </div>
    {/if}
  </form>

  <section>
    <h2>{m.files_title()}</h2>
    {#if id === undefined}
      <p class="muted">{m.files_after_save()}</p>
    {:else}
      <ul class="list">
        {#each attachments as attachment (attachment.id)}
          <li>
            <a href={app.api.attachmentUrl(attachment.id)} target="_blank" rel="noopener">{attachment.filename}</a>
            <small class="muted">{fileSize(attachment.size)}</small>
            {#if !locked}
              <button type="button" class="link" onclick={() => detach(attachment)}>{m.file_remove()}</button>
            {/if}
          </li>
        {/each}
      </ul>
      {#if !locked}
        <label class="button secondary">
          {m.files_add()}
          <input type="file" accept="application/pdf,image/*" multiple hidden onchange={attach} />
        </label>
      {/if}
    {/if}
  </section>
{/if}
