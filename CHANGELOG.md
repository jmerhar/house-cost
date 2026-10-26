# Changelog

Every release of House costs, newest first. The image is `ghcr.io/jmerhar/house-cost`. Versions
follow semantic versioning: a major release needs something done by whoever runs it, and says
what under **Upgrading**. Before 1.0, a minor release may.

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
