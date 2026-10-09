# Findings example and bundle scope

Run `python examples/synthetic_demo.py --out artifacts/demo` from the project checkout to generate a **SYNTHETIC**, valid bundle and findings pair. Generated IDs are real IDs of synthetic evidence, not live GitHub observations.

Shape (replace placeholder only with an existing ID from the selected bundle):

```json
{
  "schema_version": "0.1",
  "findings": [{
    "claim": "The selected check run reports success",
    "status": "supported",
    "rationale": "The cited checks evidence explicitly reports completed and success at the recorded head SHA.",
    "evidence_ids": ["REPLACE_WITH_EXISTING_EVIDENCE_ID"],
    "counterevidence": ["Green CI does not establish test adequacy."],
    "counterevidence_ids": [],
    "limitations": ["Only sampled head check-runs were inspected; not all CI history."]
  }]
}
```

The placeholder is intentionally invalid until replaced. `counterevidence_ids` is optional; if supplied, every ID must exist. Counterevidence text is required even if an empty array is justified. At least one explicit limitation is required. A valid reference does not prove semantic truth. Human reviewer should open source URLs and compare file/review details and SHA.

Without findings, report is an inventory marked not AI-reviewed. Outputs: report.md, report.html (escaped cards, source links and collapsible evidence), card.svg (summary counts, sampling, errors; no personal score). Do not publish a real account report automatically.
