"""The direct-mail round agent: plans each monthly round, builds the mailing file, and learns from the results.

The model reads (directions in email, anomalies, the brief); deterministic code decides (suppressions, selection,
budget, checks); a person approves the file before it goes to print.
"""
