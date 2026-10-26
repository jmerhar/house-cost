<script lang="ts">
  import { onMount } from "svelte";
  import type { AuditEntry } from "../lib/api";
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { euros, moment } from "../lib/format";
  import { m } from "../paraglide/messages.js";

  const PAGE = 50;
  const app = useApp();
  let entries = $state<AuditEntry[]>([]);
  let total = $state(0);
  let loaded = $state(false);
  let error = $state("");

  async function load(more = false): Promise<void> {
    try {
      const page = await app.api.audit({ limit: PAGE, offset: more ? entries.length : 0 });
      entries = more ? [...entries, ...page.items] : page.items;
      total = page.total;
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      loaded = true;
    }
  }

  onMount(() => {
    load();
  });

  const ACTIONS: Record<string, () => string> = {
    create: m.action_create,
    update: m.action_update,
    delete: m.action_delete,
    attach: m.action_attach,
    detach: m.action_detach,
    close: m.action_close,
  };
  const ENTITIES: Record<string, () => string> = {
    bill: m.entity_bill,
    settlement: m.entity_settlement,
    rule: m.entity_rule,
    household: m.entity_household,
    person: m.entity_person,
    category: m.entity_category,
    settings: m.entity_settings,
    reconciliation: m.entity_reconciliation,
    supplier: m.entity_supplier,
    service: m.entity_service,
    document: m.entity_document,
    passkey: m.entity_passkey,
  };

  /** A few words on what the record was: a bill's supplier and total, a person's name. */
  function detail(entry: AuditEntry): string {
    const record = (entry.after ?? entry.before ?? {}) as Record<string, unknown>;
    const parts: string[] = [];
    for (const key of ["supplier", "description", "name", "filename"]) {
      if (typeof record[key] === "string" && record[key]) parts.push(record[key] as string);
    }
    for (const key of ["total_cents", "amount_cents"]) {
      if (typeof record[key] === "number") parts.push(euros(record[key] as number));
    }
    return parts.join(" · ");
  }

  function link(entry: AuditEntry): string | null {
    return entry.entity === "bill" && entry.action !== "delete" && entry.entity_id ? `/bills/${entry.entity_id}` : null;
  }
</script>

<h1>{m.activity_title()}</h1>
{#if error}
  <p role="alert">{error}</p>
{:else if !loaded}
  <p>{m.loading()}</p>
{:else if entries.length === 0}
  <p>{m.activity_empty()}</p>
{:else}
  <ul class="list">
    {#each entries as entry (entry.id)}
      <li>
        <span class="what">
          <span>
            <strong>{entry.person_name ?? m.activity_someone()}</strong>
            {(ACTIONS[entry.action] ?? (() => entry.action))()}
            {#if link(entry)}
              <a href={link(entry)}>{(ENTITIES[entry.entity] ?? (() => entry.entity))()}</a>
            {:else}
              {(ENTITIES[entry.entity] ?? (() => entry.entity))()}
            {/if}
          </span>
          {#if detail(entry)}<small>{detail(entry)}</small>{/if}
        </span>
        <small class="when">{moment(entry.at)}</small>
      </li>
    {/each}
  </ul>
  {#if entries.length < total}
    <button type="button" class="secondary" onclick={() => load(true)}>{m.show_more()}</button>
  {/if}
{/if}
