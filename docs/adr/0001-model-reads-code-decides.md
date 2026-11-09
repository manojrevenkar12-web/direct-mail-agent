# 1. The model reads; code decides; a person approves

## Decision

The model has three jobs: turn the team's emails into directions (with the sentence each one comes from), say what
an anomaly most likely is and who should look, and write the brief the approver reads. Everything that decides who
gets a letter is code: suppressions, cells, the budget, the checks on the file. The printer receives a file only
with an approval of that file's hash by the Head of Direct Acquisition.

## Why

Choosing who to mail is arithmetic over a million rows, and the evaluation shows a plain for-loop does it as well as
the agent (the same profit on every seed). What a for-loop cannot do is read "please leave restaurants, pubs and
cafes out of this round" or tell a seasonal dip from a broken tracking link. That is where the model earns its
place, and in the evaluation it cut a person's time from 138 minutes a round (the for-loop, with someone typing
directions into a form) to 20.

## Consequences

A direction the checks do not accept becomes a question for a person, never a guess. An unguarded model following
the same emails sent 12,056 letters a year to businesses that had objected, are on the Mailing Preference Service or
have gone away; the agent sent none.
