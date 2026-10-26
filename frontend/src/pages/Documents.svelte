<script lang="ts">
  import { onMount } from "svelte";
  import type { DocumentMatch, DocumentUpdate, Service, Supplier } from "../lib/api";
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { day, fileSize } from "../lib/format";
  import { m } from "../paraglide/messages.js";

  type Kind = DocumentUpdate["kind"] & string;
  const KINDS: Kind[] = ["contract", "terms", "agreement", "bill", "info", "other"];

  const app = useApp();
  let documents = $state<DocumentMatch[]>([]);
  let suppliers = $state<Supplier[]>([]);
  let services = $state<Service[]>([]);
  let loaded = $state(false);
  let error = $state("");
  let q = $state("");
  let kind = $state("");
  let serviceFilter = $state(new URLSearchParams(location.search).get("service") ?? "");

  async function load(): Promise<void> {
    error = "";
    try {
      documents = await app.api.documents({ q, kind, service_id: serviceFilter });
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      loaded = true;
    }
  }

  async function loadLinks(): Promise<void> {
    try {
      [suppliers, services] = await Promise.all([app.api.suppliers(), app.api.services()]);
    } catch (failure) {
      error = errorMessage(failure);
    }
  }

  let timer: ReturnType<typeof setTimeout> | undefined;
  function search(): void {
    clearTimeout(timer);
    timer = setTimeout(() => load(), 250);
  }

  onMount(() => {
    load();
    loadLinks();
    return () => clearTimeout(timer);
  });

  function kindName(value: string): string {
    const names: Record<string, () => string> = {
      contract: m.kind_contract,
      terms: m.kind_terms,
      agreement: m.kind_agreement,
      bill: m.kind_bill,
      info: m.kind_info,
      other: m.kind_other,
    };
    return (names[value] ?? (() => value))();
  }

  const supplierName = (id: number | null) => suppliers.find((s) => s.id === id)?.name;
  const serviceName = (id: number | null) => services.find((s) => s.id === id)?.name;

  // --- The form: a new document (a file to upload) or one being edited ---
  type Form = {
    id: number | null;
    file: File | null;
    title: string;
    kind: Kind;
    dated: string;
    supplierId: string;
    serviceId: string;
    notes: string;
  };
  let form = $state<Form | null>(null);
  let busy = $state(false);

  function pick(event: Event): void {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (!file) return;
    form = {
      id: null,
      file,
      title: file.name.replace(/\.[^.]+$/, ""),
      kind: "contract",
      dated: "",
      supplierId: "",
      serviceId: serviceFilter,
      notes: "",
    };
    (event.currentTarget as HTMLInputElement).value = "";
  }

  function edit(document: DocumentMatch): void {
    form = {
      id: document.id,
      file: null,
      title: document.title,
      kind: document.kind as Kind,
      dated: document.dated ?? "",
      supplierId: document.supplier_id ? String(document.supplier_id) : "",
      serviceId: document.service_id ? String(document.service_id) : "",
      notes: document.notes,
    };
  }

  async function save(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const current = form;
    if (!current) return;
    busy = true;
    error = "";
    const details: DocumentUpdate = {
      title: current.title,
      kind: current.kind,
      dated: current.dated || null,
      supplier_id: current.supplierId ? Number(current.supplierId) : null,
      service_id: current.serviceId ? Number(current.serviceId) : null,
      notes: current.notes,
    };
    try {
      if (current.id === null && current.file) await app.api.addDocument(current.file, details);
      else if (current.id !== null) await app.api.updateDocument(current.id, details);
      form = null;
      await load();
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      busy = false;
    }
  }

  async function remove(id: number): Promise<void> {
    if (!confirm(m.confirm_delete_document())) return;
    try {
      await app.api.deleteDocument(id);
      form = null;
      await load();
    } catch (failure) {
      error = errorMessage(failure);
    }
  }
</script>

<div class="heading">
  <h1>{m.documents_title()}</h1>
  <label class="button">
    {m.document_add()}
    <input type="file" accept="application/pdf,image/*" hidden onchange={pick} />
  </label>
</div>

<div class="filters">
  <label class="grow">
    {m.search_label()}
    <input type="search" bind:value={q} oninput={search} placeholder={m.documents_search_placeholder()} />
  </label>
  <label>
    {m.field_kind()}
    <select bind:value={kind} onchange={() => load()}>
      <option value="">{m.kind_all()}</option>
      {#each KINDS as value (value)}<option {value}>{kindName(value)}</option>{/each}
    </select>
  </label>
  <label>
    {m.field_service()}
    <select bind:value={serviceFilter} onchange={() => load()}>
      <option value="">{m.filter_anyone()}</option>
      {#each services as service (service.id)}<option value={String(service.id)}>{service.name}</option>{/each}
    </select>
  </label>
</div>

{#if error}<p role="alert">{error}</p>{/if}

{#if form}
  <form class="card" onsubmit={save}>
    <h2>{form.id === null ? m.document_add() : m.document_edit()}</h2>
    {#if form.file}<p class="muted">{form.file.name} · {fileSize(form.file.size)}</p>{/if}
    <div class="grid">
      <label class="wide">{m.field_title()}<input bind:value={form.title} required maxlength="300" /></label>
      <label>
        {m.field_kind()}
        <select bind:value={form.kind}>
          {#each KINDS as value (value)}<option {value}>{kindName(value)}</option>{/each}
        </select>
      </label>
      <label>{m.field_dated()}<input type="date" bind:value={form.dated} /></label>
      <label>
        {m.field_supplier()}
        <select bind:value={form.supplierId}>
          <option value="">—</option>
          {#each suppliers as supplier (supplier.id)}<option value={String(supplier.id)}>{supplier.name}</option>{/each}
        </select>
      </label>
      <label>
        {m.field_service()}
        <select bind:value={form.serviceId}>
          <option value="">—</option>
          {#each services as service (service.id)}<option value={String(service.id)}>{service.name}</option>{/each}
        </select>
      </label>
      <label class="wide">{m.field_notes()}<input bind:value={form.notes} maxlength="2000" /></label>
    </div>
    <div class="actions">
      <button type="submit" disabled={busy}>{busy ? m.saving() : m.save()}</button>
      <button type="button" class="secondary" onclick={() => (form = null)}>{m.cancel()}</button>
      {#if form.id !== null}
        {@const id = form.id}
        <button type="button" class="danger" onclick={() => remove(id)}>{m.delete()}</button>
      {/if}
    </div>
  </form>
{/if}

{#if !loaded}
  <p>{m.loading()}</p>
{:else if documents.length === 0}
  <p>{q || kind || serviceFilter ? m.documents_none_match() : m.documents_empty()}</p>
{:else}
  <ul class="list">
    {#each documents as document (document.id)}
      <li>
        <span class="what">
          <a href={app.api.documentUrl(document.id)} target="_blank" rel="noopener"><strong>{document.title}</strong></a>
          <small>
            {kindName(document.kind)}
            {#if document.dated}· {day(document.dated)}{/if}
            {#if supplierName(document.supplier_id)}· {supplierName(document.supplier_id)}{/if}
            {#if serviceName(document.service_id)}· {serviceName(document.service_id)}{/if}
          </small>
          {#if document.excerpt}<small class="excerpt">{document.excerpt}</small>{/if}
          {#if !document.has_text && document.content_type === "application/pdf"}<small>{m.document_no_text()}</small>{/if}
        </span>
        <button type="button" class="link" onclick={() => edit(document)}>{m.edit()}</button>
      </li>
    {/each}
  </ul>
{/if}
