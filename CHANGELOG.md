# Changelog

Every release of House costs, newest first. The image is `ghcr.io/jmerhar/house-cost`. Versions
follow semantic versioning: a major release needs something done by whoever runs it, and says
what under **Upgrading**. Before 1.0, a minor release may.

## 0.8.0 — 2026-10-26

### Changed

- Clearer wording throughout, in English and Portuguese: balances say who "is settled up" and
  list "Suggested payments"; a household or category is deactivated with a "Deactivate" button
  that asks first, and shows an "Inactive" tag; households are reordered with "Move up"; bill
  items, minimum terms, usernames and error messages say what they mean and what to do next.
- Saving a bill says so, and says when its uploaded file could not be attached.
- Edit forms scroll into view when opened from far down a list; deleting a draft reconciliation
  asks first; empty lists say what to do.
- Notifications say when a contract renews rather than ends, and point to the contract when its
  notice period is not on file.

### Fixed

- The "Upload a bill" and "New bill" buttons line up, and file pickers can be reached from the
  keyboard.
- Drop-down lists have room for their arrow.
- The menu wraps on a phone instead of hiding its last items off-screen.
- The documents page's service filter offered "Anyone" for all services.

## 0.7.0 — 2026-10-26

### Changed

- **Upgrading:** notifications go to an email address and a phone number (Signal) instead of
  Apprise URLs. Set `NOTIFY_EMAIL_URL` and `NOTIFY_SIGNAL_URL` to the Apprise URLs to send
  through, without a recipient; a channel left unset is not offered. People enter their address
  and number on the account page, or an administrator does for them. Apprise URLs saved before
  are dropped.

## 0.6.1 — 2026-10-26

### Fixed

- A request's changes are saved before its response is sent. A browser that acted on the
  response at once, such as the first request after logging in, could find them not there yet
  and be refused as logged out.

## 0.6.0 — 2026-10-26

### Added

- Claude, optionally, with `ANTHROPIC_API_KEY` (or `ANTHROPIC_API_KEY_FILE`) and `CLAUDE_MODEL`:
  it reads the parts of a bill the app cannot, marked as read by Claude; proposes a contract's
  end date, renewal, lock-in, notice and billing interval, with a summary, for its service; and
  answers questions about a document, citing its pages. Files are sent to Anthropic's API only
  while a key is set.

## 0.5.0 — 2026-10-26

### Added

- Notifications through Apprise, set by each person on the account page: where to send them,
  which to get, and a test. A bill another household adds, a unit price that differs from the
  service's previous bill, a contract ending or a lock-in expiring in 30 and 7 days, and a
  regular bill a week overdue. Each comes in the person's language.
- A daily copy of the database in `data/backups`, from `BACKUP_TIME` (03:30), keeping
  `BACKUPS_KEPT` (14), timed by `TZ`.

### Fixed

- `COOKIE_SECURE`, `MAX_UPLOAD_BYTES` and `LOGIN_ATTEMPTS_PER_MINUTE` set in `.env` reach the
  container.

## 0.4.0 — 2026-10-26

### Added

- Reading a bill: upload its PDF or a photo and the bill form opens filled in with what it says,
  to be checked before saving. The invoice's fiscal QR code gives the date, number and total; the
  page gives the period, due date, consumption and contract dates, read by OCR where the PDF has
  no usable text. MEO Energia's and MEO's bills are read in full, others for what invoices share.
  A bill already entered is pointed out, and the service's contract dates can be updated from it.
- Consumption: electricity and water readings saved with each bill, and charted on the reports
  page.

## 0.3.0 — 2026-10-26

### Added

- Services and suppliers: what the house has with each supplier, with its references, when it
  ends or renews, its lock-in and notice period. A bill can name the service it is for.
- A document library for contracts, terms, the signed agreement and leaflets, searched by the
  text of their PDFs.

## 0.2.0 — 2026-10-26

### Added

- Passkeys: log in with a phone's or computer's fingerprint, face or screen lock instead of a
  password. Add them on the account page; set `PUBLIC_URL` so that passkeys made behind a reverse
  proxy belong to the address people use.

## 0.1.0 — 2026-10-26

### Added

- Bills split line by line by each category's rule in force on the bill's date, with the split
  fixed when the bill is saved.
- Households, people with their own logins, and categories with split rules from a date on,
  kept by an administrator.
- Balances, with the transfers that would settle everyone up, and settlements to record them.
- Files attached to bills and settlements: PDFs and photos.
- Reports by year, category and month, and a CSV export of every bill line.
- An activity log of every change and who made it.
- Optional annual reconciliation, off until an administrator turns it on.
- First-run setup in the browser, logins with sessions that last 90 days of use, and an
  interface in English and Portuguese.
