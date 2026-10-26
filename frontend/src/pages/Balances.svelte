<script lang="ts">
  import Check from "@lucide/svelte/icons/check";
  import { onMount } from "svelte";
  import type { Balances } from "../lib/api";
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { euros } from "../lib/format";
  import { m } from "../paraglide/messages.js";

  const app = useApp();
  let balances = $state<Balances | null>(null);
  let error = $state("");

  onMount(async () => {
    try {
      balances = await app.api.balances();
    } catch (failure) {
      error = errorMessage(failure);
    }
  });

  function standing(cents: number): string {
    if (cents > 0) return m.balance_owed({ amount: euros(cents) });
    if (cents < 0) return m.balance_owes({ amount: euros(-cents) });
    return m.balance_square();
  }

  const showAdjustments = $derived(Boolean(balances?.households.some((h) => h.adjustment_cents !== 0)));
</script>

<h1>{m.balances_title()}</h1>
{#if error}
  <p role="alert">{error}</p>
{:else if !balances}
  <p>{m.loading()}</p>
{:else}
  <ul class="cards">
    {#each balances.households as household (household.household_id)}
      <li class="card" class:owed={household.balance_cents > 0} class:owes={household.balance_cents < 0}>
        <strong>{household.name}</strong>
        <span class="standing">{standing(household.balance_cents)}</span>
        <dl class="figures">
          <dt>{m.col_paid()}</dt>
          <dd>{euros(household.paid_cents)}</dd>
          <dt>{m.col_share()}</dt>
          <dd>{euros(household.share_cents)}</dd>
          {#if showAdjustments}
            <dt>{m.col_adjustments()}</dt>
            <dd>{euros(household.adjustment_cents)}</dd>
          {/if}
          <dt>{m.col_sent()}</dt>
          <dd>{euros(household.sent_cents)}</dd>
          <dt>{m.col_received()}</dt>
          <dd>{euros(household.received_cents)}</dd>
        </dl>
      </li>
    {/each}
  </ul>

  <h2>{m.transfers_title()}</h2>
  {#if balances.transfers.length === 0}
    <p>{m.all_square()}</p>
  {:else}
    <ul class="list">
      {#each balances.transfers as transfer (transfer.from_id + "-" + transfer.to_id)}
        <li>
          <span>
            {m.transfer_line({
              from: app.household(transfer.from_id),
              to: app.household(transfer.to_id),
              amount: euros(transfer.amount_cents),
            })}
          </span>
          <a
            class="button secondary"
            href={`/settlements?from=${transfer.from_id}&to=${transfer.to_id}&amount=${transfer.amount_cents}`}
          >
            <Check />{m.record_transfer()}
          </a>
        </li>
      {/each}
    </ul>
  {/if}
{/if}
