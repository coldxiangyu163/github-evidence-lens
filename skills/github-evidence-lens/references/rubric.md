# Evidence rubric — no universal score

Start with the user's question, not a ranking. Each row is a question that may remain unknown.

| Dimension | Inspect | Possible support | Counterevidence / limits |
|---|---|---|---|
| Problem framing | PR body + actual patch | coherent problem, constrained change | promotional prose alone, missing reproducer |
| Implementation | files, diff hunks, scope | explicit boundary handling, understandable design | patch truncation, generated or vendored files, no surrounding code |
| Verification | changed test code and head check-runs | relevant assertions, explicit completed/success run | weak assertions, skipped jobs, SHA mismatch, legacy checks not collected |
| Collaboration | reviews, comments, author_association and actor type | specific feedback handled with evidence | bot approval, self review, unresolved objection, unseen later revisions |
| Maintenance | sampled fix/refactor discussion | clear migration or regression rationale | one PR is not longitudinal reliability |
| Scope of ownership | PR author login and repo namespace | account-authored public PR, limited claim | pair work, copied code, team or AI assistance cannot be determined |

Statuses:
- **supported**: inspected evidence supports the narrow factual claim, with limitations.
- **partial**: some supporting evidence but gaps or material contrary cues.
- **contradicted**: cited evidence conflicts with the claim; describe the conflict, do not label a person.
- **unknown**: data absent, truncated, inaccessible or too ambiguous.

Each finding: claim + evidence IDs + rationale + counterevidence + limitations. If bot/human provenance is uncertain say so. Avoid converting stars, LOC, commit counts, review counts or merge rates into capability. Separate all machine counts from judgments. Independent review, personal authorship, job fit and percentile claims require evidence beyond an account's public PR list and often cannot be established here.

Counterexample check: could the same observation arise from self-controlled org, routine formatting, generated content, partial logs or missing history? If yes, narrow the claim. Stop when the question is answered at the available evidence level; do not fill empty categories with guesses.
