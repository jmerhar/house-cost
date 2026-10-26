<script lang="ts">
  import { onMount } from "svelte";
  import type { ReadingPoint, Summary } from "../lib/api";
  import { useApp } from "../lib/context";
  import { errorMessage } from "../lib/errors";
  import { day, euros, monthName } from "../lib/format";
  import { intlLocale } from "../lib/language";
  import { m } from "../paraglide/messages.js";

  const app = useApp();
  let summary = $state<Summary | null>(null);
  let error = $state("");

  async function load(year?: number): Promise<void> {
    error = "";
    try {
      summary = await app.api.summary(year);
    } catch (failure) {
      error = errorMessage(failure);
    }
  }

  let readings = $state<ReadingPoint[]>([]);

  onMount(() => {
    load();
    app.api.readings().then(
      (points) => (readings = points),
      () => {
        // The consumption section stays empty; the summary reports its own failures.
      },
    );
  });

  /** Each measured quantity's readings, and the largest, for the bars' scale. */
  const consumption = $derived(
    (["electricity_kwh", "water_m3"] as const)
      .map((quantity) => {
        const points = readings.filter((point) => point.quantity === quantity);
        return { quantity, points, largest: Math.max(1, ...points.map((point) => point.value)) };
      })
      .filter((group) => group.points.length),
  );

  const households = $derived(summary?.shares.map((share) => share.household_id) ?? []);
  const largest = $derived(Math.max(1, ...(summary?.months.map((month) => month.total_cents) ?? [1])));
</script>

<div class="heading">
  <h1>{m.reports_title()}</h1>
  {#if summary}
    <a class="button secondary" href={app.api.csvUrl(summary.year)} download>{m.download_csv()}</a>
  {/if}
</div>

{#if error}
  <p role="alert">{error}</p>
{:else if !summary}
  <p>{m.loading()}</p>
{:else}
  {#if summary.years.length > 1}
    <label>
      {m.filter_year()}
      <select value={String(summary.year)} onchange={(event) => load(Number((event.currentTarget as HTMLSelectElement).value))}>
        {#each summary.years as year (year)}<option value={String(year)}>{year}</option>{/each}
      </select>
    </label>
  {/if}

  {#if summary.categories.length === 0}
    <p>{m.report_empty({ year: summary.year })}</p>
  {:else}
    <h2>{m.report_by_category()} · {summary.year}</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">{m.field_category()}</th>
            {#each households as household (household)}<th scope="col" class="num">{app.household(household)}</th>{/each}
            <th scope="col" class="num">{m.report_total()}</th>
          </tr>
        </thead>
        <tbody>
          {#each summary.categories as category (category.category_id)}
            <tr>
              <th scope="row">{category.name}</th>
              {#each category.shares as share (share.household_id)}<td class="num">{euros(share.amount_cents)}</td>{/each}
              <td class="num">{euros(category.total_cents)}</td>
            </tr>
          {/each}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">{m.report_total()}</th>
            {#each summary.shares as share (share.household_id)}<td class="num">{euros(share.amount_cents)}</td>{/each}
            <td class="num">{euros(summary.total_cents)}</td>
          </tr>
        </tfoot>
      </table>
    </div>

    <h2>{m.report_by_month()}</h2>
    <ul class="bars">
      {#each summary.months as month (month.month)}
        <li>
          <span class="label">{monthName(month.month)}</span>
          <span class="bar" style:width={`${(month.total_cents / largest) * 100}%`}></span>
          <span class="num">{euros(month.total_cents)}</span>
        </li>
      {/each}
    </ul>
  {/if}
{/if}

{#each consumption as group (group.quantity)}
  <h2>{group.quantity === "electricity_kwh" ? m.consumption_electricity() : m.consumption_water()}</h2>
  <ul class="bars">
    {#each group.points as point (point.bill_id)}
      <li>
        <span class="label">{day(point.period_end ?? point.date)}</span>
        <span class="bar" style:width={`${(point.value / group.largest) * 100}%`}></span>
        <span class="num">
          {point.value.toLocaleString(intlLocale())} {group.quantity === "electricity_kwh" ? "kWh" : "m³"}
          {#if point.unit_price !== null}<small class="muted">· {point.unit_price}</small>{/if}
        </span>
      </li>
    {/each}
  </ul>
{/each}
