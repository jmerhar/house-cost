/** What to tell a person when a request fails, in their language. */

import { ApiError } from "./api";
import { m } from "../paraglide/messages.js";

/** The message for each of the API's refusal codes. */
const BY_CODE: Record<string, () => string> = {
  invalid_login: m.error_invalid_login,
  too_many_attempts: m.error_too_many_attempts,
  no_rule: m.error_no_rule,
  period_closed: m.error_period_closed,
  name_taken: m.error_name_taken,
  login_taken: m.error_login_taken,
  last_admin: m.error_last_admin,
  rule_in_use: m.error_rule_in_use,
  rule_exists_on_date: m.error_rule_exists_on_date,
  unsupported_file: m.error_unsupported_file,
  too_large: m.error_too_large,
  wrong_password: m.error_wrong_password,
  no_contact: m.error_no_contact,
  invalid_email: m.error_invalid_email,
  invalid_phone: m.error_invalid_phone,
  claude_off: m.error_claude_off,
  claude_failed: m.error_claude_failed,
  claude_declined: m.error_claude_declined,
  overlaps_closed_period: m.error_overlaps_closed_period,
  already_closed: m.error_already_closed,
  already_set_up: m.error_already_set_up,
  invalid: m.error_invalid,
  passkey_rejected: m.error_passkey_rejected,
  passkey_unknown: m.error_passkey_unknown,
  passkey_expired: m.error_passkey_expired,
  passkey_exists: m.error_passkey_exists,
  supplier_exists: m.error_supplier_exists,
  read_timeout: m.error_read_timeout,
  unreadable: m.error_unreadable,
};

/** A failure as a sentence: the API's own reason where it has one this interface knows. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return m.error_offline();
    const known = BY_CODE[error.message];
    if (known) return known();
    return m.error_other({ detail: error.message });
  }
  return m.error_other({ detail: error instanceof Error ? error.message : String(error) });
}
