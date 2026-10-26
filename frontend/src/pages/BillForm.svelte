<script lang="ts">
  import Paperclip from "@lucide/svelte/icons/paperclip";
  import Plus from "@lucide/svelte/icons/plus";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import X from "@lucide/svelte/icons/x";
  import { onMount } from "svelte";
  import type { Attachment, Bill, BillIn, Reading, Service, ServiceIn, Supplier } from "../lib/api";
  import { takeDraft } from "../lib/draft";
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { amountInput, day, euros, fileSize, parseAmount, today } from "../lib/format";
  import { navigate } from "../lib/router.svelte";
  import { intlLocale } from "../lib/language";
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
  let readings = $state<Reading[]>([]);
  // A bill read from a file opens with what was read; nothing is saved until it is checked.
  // svelte-ignore state_referenced_locally
  const draft = id === undefined ? takeDraft() : null;
  /** The contract changes the read bill reported, and whether to apply each on saving. */
  let changes = $state<{ field: "ends_on" | "renews_automatically" | "lock_in_until"; value: string | boolean; apply: boolean }[]>([]);
  let previews = $state<Record<number, Preview>>({});

  // A read bill without a service offers to set one up from what the bill says, with its
  // supplier added too when it is not on file, so one upload leaves all three in place.
  let addService = $state(true);
  let serviceName = $state("");
  const offerService = $derived(draft !== null && serviceId === "");
  const newSupplier = $derived(draft !== null && draft.proposal.supplier_id === null && supplier.trim() !== "");
  /** The name a new service gets when none is typed: its category, else its supplier. */
  const suggestedServiceName = $derived(lines[0]?.categoryId ? app.category(Number(lines[0].categoryId)) : supplier.trim());
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
    readings = bill.readings;
    lines = bill.lines.map((line) => ({
      key: nextKey++,
      id: line.id,
      description: line.description,
      categoryId: String(line.category_id),
      amount: amountInput(line.amount_cents),
    }));
  }

  if (draft) {
    const read = draft.proposal;
    if (read.date) date = read.date;
    supplier = read.supplier_name ?? "";
    invoice = read.invoice_number ?? "";
    periodStart = read.period_start ?? "";
    periodEnd = read.period_end ?? "";
    due = read.due_date ?? "";
    serviceId = read.service_id ? String(read.service_id) : "";
    readings = read.readings;
    if (read.lines.length) {
      lines = read.lines.map((line) => ({
        key: nextKey++,
        id: null,
        description: line.description,
        categoryId: line.category_id ? String(line.category_id) : "",
        amount: amountInput(line.amount_cents),
      }));
    }
    const reported = read.service_changes;
    changes = (["ends_on", "renews_automatically", "lock_in_until"] as const)
      .filter((field) => reported[field] !== null && reported[field] !== undefined)
      .map((field) => ({ field, value: reported[field] as string | boolean, apply: true }));
  }

  /** The QR code vouches for these; the rest was read from the page and needs a look. */
  const vouched = $derived(
    Object.entries(draft?.proposal.sources ?? {})
      .filter(([, source]) => source === "qr")
      .map(([field]) => field),
  );

  function changeText(change: (typeof changes)[number]): string {
    if (change.field === "ends_on") return m.service_ends_on_change({ date: day(String(change.value)) });
    if (change.field === "lock_in_until") return m.service_lock_in({ date: day(String(change.value)) });
    return change.value ? m.field_renews() : m.service_no_renewal();
  }

  async function applyChanges(): Promise<void> {
    const service = services.find((s) => String(s.id) === serviceId);
    const wanted = changes.filter((change) => change.apply);
    if (!service || !wanted.length) return;
    const { id: serviceKey, ...fields } = service;
    const body: ServiceIn = { ...fields };
    for (const change of wanted) Object.assign(body, { [change.field]: change.value });
    await app.api.updateService(serviceKey, body);
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
      readings,
      lines: parsed.map(({ line, cents }) => ({
        id: line.id,
        description: line.description,
        category_id: Number(line.categoryId),
        amount_cents: cents as number,
      })),
    };
  }

  /** After a read bill is saved: add its supplier if it is not on file, and the service it was
   *  offered, then link the bill to that service. Whether all of that went through. */
  async function setUpFromBill(billId: number, payload: BillIn): Promise<boolean> {
    if (!draft) return true;
    const read = draft.proposal;
    const categoryId = payload.lines[0]?.category_id ?? null;
    try {
      let supplierId = read.supplier_id;
      if (newSupplier) {
        const added = await app.api.createSupplier({
          name: supplier.trim(),
          nif: read.issuer_nif,
          default_category_id: categoryId,
          notes: "",
          active: true,
        });
        supplierId = added.id;
      }
      if (offerService && addService && supplierId !== null) {
        const service = await app.api.createService({
          supplier_id: supplierId,
          name: serviceName.trim() || suggestedServiceName,
          identifiers: read.identifiers,
          default_category_id: categoryId,
          starts_on: null,
          ends_on: read.contract.ends_on,
          renews_automatically: read.contract.renews_automatically ?? true,
          lock_in_until: read.contract.lock_in_until,
          notice_days: null,
          billed_every_days: read.contract.billed_every_days,
          notes: "",
          active: true,
        });
        await app.api.updateBill(billId, { ...payload, service_id: service.id });
      }
      return true;
    } catch {
      return false;
    }
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
      if (id === undefined) {
        const created = await app.api.createBill(payload);
        if (draft) {
          // The bill is saved; its file and the contract dates follow, and a failure of either
          // leaves the bill as it is, to be finished on its own page.
          const attached = await app.api.attach(draft.file, { bill_id: created.id }).then(
            () => true,
            () => false,
          );
          await applyChanges().catch(() => undefined);
          if (!(await setUpFromBill(created.id, payload))) {
            app.say(m.setup_from_bill_failed(), `/bills/${created.id}`, true);
            navigate(`/bills/${created.id}`, { replace: true });
            return;
          }
          if (!attached) {
            app.say(m.file_attach_failed(), `/bills/${created.id}`, true);
            navigate(`/bills/${created.id}`, { replace: true });
            return;
          }
        }
        app.say(m.bill_saved(), `/bills/${created.id}`);
        navigate(`/bills/${created.id}`, { replace: true });
      } else {
        await app.api.updateBill(id, payload);
        app.say(m.bill_saved(), "/bills");
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
  {#if draft}
    <div class="note">
      <p><strong>{m.read_banner({ file: draft.file.name })}</strong></p>
      {#if vouched.length}<p>{m.read_vouched()}</p>{/if}
      {#if draft.proposal.text_source === "ocr"}<p>{m.read_ocr()}</p>{/if}
      {#if draft.proposal.warnings.includes("total_mismatch")}<p class="problem">{m.read_total_mismatch()}</p>{/if}
      {#if draft.proposal.warnings.includes("lines_dropped")}<p>{m.read_lines_dropped()}</p>{/if}
      {#if Object.values(draft.proposal.sources).includes("claude")}<p>{m.read_claude()}</p>{/if}
      {#if draft.proposal.warnings.some((w) => w.startsWith("claude_"))}<p>{m.read_claude_failed()}</p>{/if}
      {#if newSupplier}
        <p>{m.read_new_supplier({ name: supplier.trim() })}</p>
      {:else if !draft.proposal.supplier_id && draft.proposal.issuer_nif}
        <p>{m.read_unknown_supplier({ nif: draft.proposal.issuer_nif })}</p>
      {/if}
      {#if draft.proposal.duplicate_bill_id}
        <p class="problem">
          {m.read_duplicate()} <a href={`/bills/${draft.proposal.duplicate_bill_id}`}>{m.read_duplicate_open()}</a>
        </p>
      {/if}
    </div>
  {/if}
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
                <input bind:value={line.amount} inputmode="decimal" required placeholder={amountInput(0)} />
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
                <X />{m.line_remove()}
              </button>
            {/if}
          </li>
        {/each}
      </ol>
      <button type="button" class="secondary" onclick={() => (lines = [...lines, blankLine()])}><Plus />{m.line_add()}</button>
      <p class="total">{m.total_label()}: <strong>{euros(totalCents)}</strong></p>

      {#if readings.length}
        <ul class="list">
          {#each readings as reading, index (index)}
            <li>
              {reading.quantity === "electricity_kwh"
                ? m.reading_kwh({ value: reading.value.toLocaleString(intlLocale()), price: reading.unit_price ?? "—" })
                : m.reading_m3({ value: reading.value.toLocaleString(intlLocale()), price: reading.unit_price ?? "—" })}
            </li>
          {/each}
        </ul>
      {/if}
      {#if draft && offerService && (draft.proposal.supplier_id !== null || newSupplier)}
        {@const contract = draft.proposal.contract}
        {@const references = Object.entries(draft.proposal.identifiers)}
        <fieldset class="card">
          <legend><label class="check"><input type="checkbox" bind:checked={addService} /> {m.service_from_bill()}</label></legend>
          {#if addService}
            <label>{m.field_service_name()}<input bind:value={serviceName} maxlength="200" placeholder={suggestedServiceName} /></label>
            <ul class="muted">
              {#if references.length}<li>{m.service_references({ list: references.map(([k, v]) => `${k} ${v}`).join(", ") })}</li>{/if}
              {#if contract.ends_on}
                <li>{contract.renews_automatically === false ? m.service_ends({ date: day(contract.ends_on) }) : m.service_renews({ date: day(contract.ends_on) })}</li>
              {/if}
              {#if contract.lock_in_until}<li>{m.service_lock_in({ date: day(contract.lock_in_until) })}</li>{/if}
              {#if contract.billed_every_days}<li>{m.terms_billed_every({ days: contract.billed_every_days })}</li>{/if}
            </ul>
          {/if}
        </fieldset>
      {/if}
      {#if changes.length}
        <fieldset class="card">
          <legend>{m.service_changes_title()}</legend>
          {#each changes as change (change.field)}
            <label class="check"><input type="checkbox" bind:checked={change.apply} /> {changeText(change)}</label>
          {/each}
        </fieldset>
      {/if}

      <label>{m.field_notes()}<textarea bind:value={notes} rows="3" maxlength="2000"></textarea></label>
    </fieldset>

    {#if error}<p role="alert">{error}</p>{/if}
    {#if !locked}
      <div class="actions">
        <button type="submit" disabled={busy}>{busy ? m.saving() : m.save()}</button>
        <a class="button secondary" href="/bills">{m.cancel()}</a>
        {#if id !== undefined}
          <button type="button" class="danger apart" onclick={remove}><Trash2 />{m.delete()}</button>
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
              <button type="button" class="link" onclick={() => detach(attachment)}><X />{m.file_remove()}</button>
            {/if}
          </li>
        {/each}
      </ul>
      {#if !locked}
        <label class="button secondary">
          <Paperclip />{m.files_add()}
          <input type="file" accept="application/pdf,image/*" multiple class="file-input" onchange={attach} />
        </label>
      {/if}
    {/if}
  </section>
{/if}
