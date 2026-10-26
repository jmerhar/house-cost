# A parser for SMAS (water) bills

`extraction/parsers.py` reads MEO Energia's and MEO's bills in full, chosen by the issuer's NIF;
other issuers get the generic parser (number, date, total, due date). No SMAS bill has
arrived yet to write one from.

- When the first SMAS bill arrives: add it to the ignored `samples/` with its expected values in
  `samples/expected.json`, and check what its QR code and text layer give.
- Write `smas(text)` in `parsers.py` and register it under SMAS's NIF in `BY_NIF`: period,
  consumption in m³ and its price (`water_m3` readings), the meter reference, and the bill's parts
  (water, sanitation, waste, fees) as lines.
- Test it with a synthetic bill in `tests/synthetic.py` laid out like the real one; real bills never
  go in the repository.
