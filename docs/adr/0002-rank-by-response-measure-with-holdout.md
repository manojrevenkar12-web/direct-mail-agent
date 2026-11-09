# 2. Rank by response, measure with a small holdout

## Context

Mail's value is what it adds: applications from mailed businesses minus those that would have come anyway. The
first design learned that per cell from a 10% holdout in every cell and ranked by it.

## What happened

At application rates under 1%, a cell's holdout of a few thousand businesses is noise, and every held-out business
is a letter not sent. On the first held-out split the design earned +4.1% over today's process; learning from the
mailed arm alone earned +14.3%. Two more flaws made it worse: every cell started from the same prior (ignoring the
existing predictive models) and cells kept only for learning had about 110 holdouts.

## Decision

Start every cell from the existing models' prediction. Rank cells by the mailed arm's applications, funding and
value, learned round by round. Keep one 5% random holdout across the file, not to rank but to measure what the round
was worth.

## Consequences

On the second held-out split: +16.2% over today's process. Without the holdout it would be +19.6%: measuring costs
about £54,000 a year in this market. Without it the only measure is matchback, which put the applications mail
caused at 6.1 times the truth; the holdout put them at 0.92 times. That is the number a budget should be set with,
and the trade-off is the Head of Direct Acquisition's to make (`limits.holdout_share`).
