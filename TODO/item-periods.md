# Periods per bill line?

MEO's invoice gives a period per item ("14 set a 30 set") rather than one for the whole bill. The
MEO parser takes the span, earliest start to latest end, as the bill's period, which is all the app
uses a period for: charting readings, estimating how often a service bills, and showing it.

- Look again once the next MEO bill arrives (the first one covers a partial month, 14 to 30 Sep
  2026): whether a full month's items share one period, and whether anything would use a period
  per line, such as splitting a part-month by the days each household had a service.
- A bill line is one of MEO's groups (Package, Mobile, Activation), which mix items with different
  periods, so a per-line period would itself be a span or need lines per item.
