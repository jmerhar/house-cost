/**
 * Money, percentages and dates as people read and type them, in the interface's language.
 *
 * Amounts travel as whole cents and shares as basis points (1/100 of a percent); only this module
 * turns them into text and back.
 */

import * as format from "@jmerhar/jigkit/format";
import { intlLocale } from "./language";

export { parseAmount, parsePercent, percentInput } from "@jmerhar/jigkit/format";

/** Cents as euros: "€287.59" in English, "287,59 €" in Portuguese. */
export const euros = (cents: number, locale: string = intlLocale()): string => format.euros(cents, locale);

/** Cents as the plain number an amount field shows for editing: "287.59" or "287,59". */
export const amountInput = (cents: number, locale: string = intlLocale()): string => format.amountInput(cents, locale);

/** Basis points as a percentage: 5000 → "50%", 3333 → "33.33%" (or "33,33%"). */
export const percent = (basisPoints: number, locale: string = intlLocale()): string => format.percent(basisPoints, locale);

/** An ISO date as people read it: "18 Oct 2026" in English, "18/10/2026" in Portuguese. */
export const day = (iso: string, locale: string = intlLocale()): string => format.day(iso, locale);

/** A moment as people read it, in their own time zone: "18 Oct 2026, 14:05". */
export const moment = (iso: string, locale: string = intlLocale()): string => format.moment(iso, locale);

/** A month's name, 1 for January: "October", "outubro". */
export const monthName = (month: number, locale: string = intlLocale()): string => format.monthName(month, locale);

/** Today's date in the person's own time zone, as ISO. */
export const today = (now: Date = new Date()): string => format.calendarDate(now);

/** A file's size as people read it: "312 kB". */
export const fileSize = (bytes: number, locale: string = intlLocale()): string => format.fileSize(bytes, locale);
