# Assay

Measured results for a Forex research agent: what its strategies actually
contain, rather than what they claim.

**[View the dashboard](https://loyubu.github.io/assay-site/)**

## What this repository is

Two files: a self-contained page and the data it renders. Nothing else.

The agent itself lives in a separate, private repository. That separation is
deliberate and structural rather than a matter of care: the trading journal,
account identifiers and anything denominated in currency are not filtered out
of this repository — they were never in it, so no template mistake or
over-broad glob can expose them.

## What crosses the boundary

The build step in the private repo decides field by field what may publish,
using an allowlist rather than a blocklist. Allowlists fail closed: a field
someone forgets to add simply does not appear, instead of leaking.

Published: expectancy in R, win rates, t-statistics, trade counts, equity
curves in R, decline rates, rubric score distributions, approval latency as a
distribution.

Never published: account balance or identifier, open positions, realised profit
and loss in any currency, broker order and trade identifiers, and the clock
time of any individual decision.

Expectancy in R is dimensionless and reveals nothing. Profit and loss in pounds,
divided by a documented 1% risk per trade, gives the account size in one step —
which is why the rule is absolute rather than a judgement made at render time.

## Honest summary of what it found

Three independent rule sets have been measured on this harness — the Turtle and
Kaufman systems, a set of macro and regime factors, and the ICT methodology.
None showed an edge. That is a real result, obtained for nothing, and it is the
kind of result a research project should want early.
