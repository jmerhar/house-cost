<script lang="ts">
  import Building2 from "@lucide/svelte/icons/building-2";
  import Plug from "@lucide/svelte/icons/plug";
  import Pencil from "@lucide/svelte/icons/pencil";
  import Plus from "@lucide/svelte/icons/plus";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import { onMount } from "svelte";
  import type { Service, ServiceIn, Supplier, SupplierIn } from "../lib/api";
  import { useApp } from "../lib/context";
  import { reveal } from "../lib/reveal";
  import { errorMessage } from "../lib/errors";
  import { day, today } from "../lib/format";
  import { m } from "../paraglide/messages.js";

  /** How close a contract's end or lock-in must be to be flagged. */
  const SOON_DAYS = 60;

  const app = useApp();
  let suppliers = $state<Supplier[]>([]);
  let services = $state<Service[]>([]);
  let loaded = $state(false);
  let error = $state("");

  async function load(): Promise<void> {
    try {
      [suppliers, services] = await Promise.all([app.api.suppliers(), app.api.services()]);
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      loaded = true;
    }
  }

  onMount(() => {
    load();
  });

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

  /** Whether a date falls within the next SOON_DAYS days (or has just passed). */
  function soon(iso: string | null, now = today()): boolean {
    if (!iso) return false;
    const days = (Date.parse(iso) - Date.parse(now)) / 86_400_000;
    return days <= SOON_DAYS;
  }

  // --- Supplier form ---
  type SupplierForm = { id: number | null; name: string; nif: string; categoryId: string; notes: string; active: boolean };
  let supplierForm = $state<SupplierForm | null>(null);

  function editSupplier(supplier: Supplier | null): void {
    supplierForm = {
      id: supplier?.id ?? null,
      name: supplier?.name ?? "",
      nif: supplier?.nif ?? "",
      categoryId: supplier?.default_category_id ? String(supplier.default_category_id) : "",
      notes: supplier?.notes ?? "",
      active: supplier?.active ?? true,
    };
    reveal("#supplier-form");
  }

  async function saveSupplier(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const form = supplierForm;
    if (!form) return;
    const body: SupplierIn = {
      name: form.name,
      nif: form.nif || null,
      default_category_id: form.categoryId ? Number(form.categoryId) : null,
      notes: form.notes,
      active: form.active,
    };
    const id = form.id;
    if (await attempt(() => (id === null ? app.api.createSupplier(body) : app.api.updateSupplier(id, body)))) {
      supplierForm = null;
    }
  }

  function deleteSupplier(supplier: Supplier): void {
    if (confirm(m.confirm_delete_supplier({ name: supplier.name }))) attempt(() => app.api.deleteSupplier(supplier.id));
  }

  function deleteService(service: Service): void {
    if (confirm(m.confirm_delete_service({ name: service.name }))) attempt(() => app.api.deleteService(service.id));
  }

  // --- Service form ---
  type ServiceForm = {
    id: number | null;
    supplierId: string;
    name: string;
    identifiers: string;
    categoryId: string;
    startsOn: string;
    endsOn: string;
    renews: boolean;
    lockIn: string;
    notice: string;
    every: string;
    notes: string;
    active: boolean;
  };
  let serviceForm = $state<ServiceForm | null>(null);

  function editService(service: Service | null, supplier?: Supplier): void {
    serviceForm = {
      id: service?.id ?? null,
      supplierId: String(service?.supplier_id ?? supplier?.id ?? suppliers[0]?.id ?? ""),
      name: service?.name ?? "",
      identifiers: Object.entries(service?.identifiers ?? {})
        .map(([label, value]) => `${label}: ${value}`)
        .join("\n"),
      categoryId: String(service?.default_category_id ?? supplier?.default_category_id ?? ""),
      startsOn: service?.starts_on ?? "",
      endsOn: service?.ends_on ?? "",
      renews: service?.renews_automatically ?? true,
      lockIn: service?.lock_in_until ?? "",
      notice: service?.notice_days?.toString() ?? "",
      every: service?.billed_every_days?.toString() ?? "",
      notes: service?.notes ?? "",
      active: service?.active ?? true,
    };
    reveal("#service-form");
  }

  /** "CPE: PT0002…" lines as a map; a line without a colon is ignored. */
  function parseIdentifiers(text: string): Record<string, string> {
    const result: Record<string, string> = {};
    for (const line of text.split("\n")) {
      const at = line.indexOf(":");
      if (at > 0 && line.slice(0, at).trim()) result[line.slice(0, at).trim()] = line.slice(at + 1).trim();
    }
    return result;
  }

  async function saveService(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const form = serviceForm;
    if (!form) return;
    const body: ServiceIn = {
      supplier_id: Number(form.supplierId),
      name: form.name,
      identifiers: parseIdentifiers(form.identifiers),
      default_category_id: form.categoryId ? Number(form.categoryId) : null,
      starts_on: form.startsOn || null,
      ends_on: form.endsOn || null,
      renews_automatically: form.renews,
      lock_in_until: form.lockIn || null,
      notice_days: form.notice ? Number(form.notice) : null,
      billed_every_days: form.every ? Number(form.every) : null,
      notes: form.notes,
      active: form.active,
    };
    const id = form.id;
    if (await attempt(() => (id === null ? app.api.createService(body) : app.api.updateService(id, body)))) {
      serviceForm = null;
    }
  }
</script>

<div class="heading">
  <h1>{m.services_title()}</h1>
  {#if !supplierForm}<button type="button" onclick={() => editSupplier(null)}><Plus />{m.supplier_add()}</button>{/if}
</div>
<p class="muted">{m.services_intro()}</p>
{#if error}<p role="alert">{error}</p>{/if}

{#if supplierForm}
  <form class="card" id="supplier-form" onsubmit={saveSupplier}>
    <h2>{supplierForm.id === null ? m.supplier_add() : m.supplier_edit()}</h2>
    <div class="grid">
      <label>{m.field_name()}<input bind:value={supplierForm.name} required maxlength="200" /></label>
      <label>{m.field_nif()}<input bind:value={supplierForm.nif} inputmode="numeric" maxlength="11" /></label>
      <label>
        {m.field_default_category()}
        <select bind:value={supplierForm.categoryId}>
          <option value="">—</option>
          {#each app.categories as category (category.id)}<option value={String(category.id)}>{category.name}</option>{/each}
        </select>
      </label>
      <label class="wide">{m.field_notes()}<textarea bind:value={supplierForm.notes} rows="3" maxlength="2000"></textarea></label>
      {#if supplierForm.id !== null}
        <label class="check"><input type="checkbox" bind:checked={supplierForm.active} /> {m.active()}</label>
      {/if}
    </div>
    <div class="actions">
      <button type="submit">{m.save()}</button>
      <button type="button" class="secondary" onclick={() => (supplierForm = null)}>{m.cancel()}</button>
    </div>
  </form>
{/if}

{#if serviceForm}
  <form class="card" id="service-form" onsubmit={saveService}>
    <h2>{serviceForm.id === null ? m.service_add() : m.service_edit()}</h2>
    <div class="grid">
      <label>
        {m.field_supplier()}
        <select bind:value={serviceForm.supplierId} required>
          {#each suppliers as supplier (supplier.id)}<option value={String(supplier.id)}>{supplier.name}</option>{/each}
        </select>
      </label>
      <label>{m.field_name()}<input bind:value={serviceForm.name} required maxlength="200" /></label>
      <label class="wide">
        {m.field_identifiers()}
        <textarea bind:value={serviceForm.identifiers} rows="3" placeholder="CPE: PT0002…"></textarea>
      </label>
      <label>
        {m.field_default_category()}
        <select bind:value={serviceForm.categoryId}>
          <option value="">—</option>
          {#each app.categories as category (category.id)}<option value={String(category.id)}>{category.name}</option>{/each}
        </select>
      </label>
      <label>{m.field_billed_every()}<input type="number" min="1" bind:value={serviceForm.every} /></label>
      <label>{m.field_starts_on()}<input type="date" bind:value={serviceForm.startsOn} /></label>
      <label>{m.field_ends_on()}<input type="date" bind:value={serviceForm.endsOn} /></label>
      <label>{m.field_lock_in()}<input type="date" bind:value={serviceForm.lockIn} /></label>
      <label>{m.field_notice_days()}<input type="number" min="0" bind:value={serviceForm.notice} /></label>
      <label class="check"><input type="checkbox" bind:checked={serviceForm.renews} /> {m.field_renews()}</label>
      {#if serviceForm.id !== null}
        <label class="check"><input type="checkbox" bind:checked={serviceForm.active} /> {m.active()}</label>
      {/if}
      <label class="wide">{m.field_notes()}<textarea bind:value={serviceForm.notes} rows="3" maxlength="2000"></textarea></label>
    </div>
    <div class="actions">
      <button type="submit">{m.save()}</button>
      <button type="button" class="secondary" onclick={() => (serviceForm = null)}>{m.cancel()}</button>
    </div>
  </form>
{/if}

{#if !loaded}
  <p>{m.loading()}</p>
{:else if suppliers.length === 0}
  <p>{m.suppliers_empty()}</p>
{:else}
  {#each suppliers as supplier (supplier.id)}
    {@const own = services.filter((service) => service.supplier_id === supplier.id)}
    <article class="card">
      <div class="heading">
        <div>
          <h2 class="with-icon">
            <Building2 />{supplier.name}
            {#if !supplier.active}<small class="tag">{m.inactive()}</small>{/if}
          </h2>
          <p class="muted caption">{m.field_supplier()}{#if supplier.nif}{" · "}{m.nif_value({ nif: supplier.nif })}{/if}</p>
          {#if supplier.notes}<p class="caption notes">{supplier.notes}</p>{/if}
        </div>
        <span class="row-actions">
          <button type="button" class="link" onclick={() => editService(null, supplier)}><Plus />{m.service_add()}</button>
          <button type="button" class="link" onclick={() => editSupplier(supplier)}><Pencil />{m.edit()}</button>
          {#if !supplier.in_use}
            <button type="button" class="link danger" onclick={() => deleteSupplier(supplier)}><Trash2 />{m.supplier_delete()}</button>
          {/if}
        </span>
      </div>
      <h3 class="subheading">{m.nav_services()}</h3>
      {#if own.length === 0}<p class="muted">{m.services_none()}</p>{/if}
      <ul class="list">
        {#each own as service (service.id)}
          <li>
            <span class="what">
              <strong class="with-icon">
                <Plug />{service.name}
                {#if !service.active}<small class="tag">{m.inactive()}</small>{/if}
              </strong>
              {#each Object.entries(service.identifiers) as [label, value] (label)}
                <small>{label}: {value}</small>
              {/each}
              {#if service.ends_on}
                <small class:problem={service.active && soon(service.ends_on)}>
                  {service.renews_automatically ? m.service_renews({ date: day(service.ends_on) }) : m.service_ends({ date: day(service.ends_on) })}
                </small>
              {/if}
              {#if service.lock_in_until}
                <small class:problem={service.active && soon(service.lock_in_until)}>
                  {m.service_lock_in({ date: day(service.lock_in_until) })}
                </small>
              {/if}
              {#if service.notice_days !== null}<small>{m.service_notice({ days: service.notice_days })}</small>{/if}
              {#if service.notes}<small class="notes">{service.notes}</small>{/if}
            </span>
            <span class="row-actions">
              <a href={`/documents?service=${service.id}`}>{m.nav_documents()}</a>
              <button type="button" class="link" onclick={() => editService(service)}><Pencil />{m.edit()}</button>
              {#if !service.in_use}
                <button type="button" class="link danger" onclick={() => deleteService(service)}><Trash2 />{m.service_delete()}</button>
              {/if}
            </span>
          </li>
        {/each}
      </ul>
    </article>
  {/each}
{/if}
