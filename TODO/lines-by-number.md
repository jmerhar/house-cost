# Split a bill's lines across categories without choosing them every month

MEO's invoice mixes shared internet with personal mobiles, each in its own category with its own
split. Choosing a category per line on every bill is the effort to remove. Decide once the next MEO
bill arrives: it will carry another mobile, which makes the shape clearer.

What the first bill (21 Sep 2026) shows: MEO groups its items under numbers that stay the same from
month to month, and the parser currently makes lines of MEO's own groups (Package, Mobile,
Activation), which mix numbers and so do not map to categories.

- Nº Serviço 1700000001: the M4 package (TV + internet 500 + phone + mobile 5 GB) and its
  discounts.
- Cartão adicional (Telemóvel) and Nº 912345678: Tiago's mobile.
- Nº Serviço 1700000002: the MEOBox.

Options (leaning towards A):

- **A. One line per number, remembered on the service.** The parser makes a line per number
  section (its items and discounts summed); on the first bill each line gets a category and a
  "Remember for next bills" tick stores "number → category" on the service, editable there.
  Later bills arrive categorised.
- **B. Copy the previous bill's categories**, matching lines by number. No set-up, but the rule is
  invisible.
- **C. A template of lines per service**, with each month's amounts slotted in.

Open questions:

- The package's bundled mobile is not priced separately: share the whole package (or the whole
  bill) 50/50, or carve out a fixed amount or a percentage for that mobile.
- No special rule for small amounts: every line follows its mapping whatever its size.
