"""Data-only renderers. Citation validation is structural, never semantic."""
import html
import json
import re
from pathlib import Path

from .core import REPO, sanitize


def safe_url(url):
    if not isinstance(url, str) or not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.\-/]+(?:#[A-Za-z0-9_.-]+)?', url):
        raise ValueError('Evidence URL must be a canonical public GitHub URL')
    if any(p in ('.', '..') for p in url.split('/')):
        raise ValueError('Unsafe URL path')
    return url


def validate_bundle(bundle):
    if not isinstance(bundle, dict) or bundle.get('schema_version') != '0.1' or not isinstance(bundle.get('evidence'), list):
        raise ValueError('Unsupported evidence bundle')
    ids = set()
    for item in bundle['evidence']:
        if not isinstance(item, dict) or not re.fullmatch(r'ev_[a-f0-9]{20}', item.get('id', '')) or item['id'] in ids:
            raise ValueError('Invalid or duplicate evidence ID')
        safe_url(item.get('url'))
        if not isinstance(item.get('completeness'), dict) or not isinstance(item.get('kind'), str):
            raise ValueError('Missing evidence metadata')
        ids.add(item['id'])
    return ids


def validate_findings(findings, ids):
    if not isinstance(findings, dict) or findings.get('schema_version') != '0.1' or not isinstance(findings.get('findings'), list):
        raise ValueError('Expected findings schema_version 0.1 and findings array')
    for claim in findings['findings']:
        if not isinstance(claim, dict):
            raise ValueError('Finding must be an object')
        for key in ('claim', 'rationale'):
            if not isinstance(claim.get(key), str) or not claim[key].strip():
                raise ValueError('Finding requires nonempty ' + key)
        if claim.get('status') not in ('supported', 'partial', 'contradicted', 'unknown'):
            raise ValueError('Invalid finding status')
        citations = claim.get('evidence_ids')
        if not isinstance(citations, list) or not citations or any(not isinstance(c, str) or c not in ids for c in citations):
            raise ValueError('Each finding must cite existing evidence IDs')
        for key in ('counterevidence', 'limitations'):
            if not isinstance(claim.get(key), list) or any(not isinstance(x, str) or not x.strip() for x in claim[key]):
                raise ValueError(key + ' must be an explicit string array')
        if not claim['limitations']:
            raise ValueError('At least one limitation is required')
        counter_ids = claim.get('counterevidence_ids', [])
        if not isinstance(counter_ids, list) or any(not isinstance(c, str) or c not in ids for c in counter_ids):
            raise ValueError('Unknown counterevidence citation')
    return findings['findings']


def md(value):
    # Escape HTML first and every Markdown delimiter, including backslashes.
    value = html.escape(str(value), quote=True)
    return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', value).replace('\n', ' ')


def render(bundle, out, findings=None):
    ids = validate_bundle(bundle)
    claims = validate_findings(findings, ids) if findings is not None else []
    bundle = sanitize(bundle)
    claims = sanitize(claims)
    subject = str(bundle.get('subject', 'Agent-directed inspection'))
    reviewed = 'Agent findings supplied; human review required' if findings is not None else 'Not AI-reviewed / 未经 AI 评审：仅证据清单'
    lines = ['# GitHub Evidence Lens', '', f'Subject: {md(subject)}', '', md(reviewed), '',
             'Public evidence is not a personal score or hiring decision. Low evidence is not negative evidence.', '',
             f"Source: {md(bundle.get('source', 'unknown'))}", '', '## Machine inventory / 机器清单', '',
             f"Evidence items: {len(ids)}; collection errors: {len(bundle.get('errors', []))}", '']
    for k, v in bundle.get('counts', {}).items():
        lines.append(f'- {md(k)}: {md(v)}')
    lines += ['', '## Coverage and budgets / 覆盖与预算', '']
    for k in ('budget', 'coverage', 'selection', 'errors', 'limitations'):
        lines += [f'- {k}: {md(json.dumps(bundle.get(k, {}), ensure_ascii=False))}']
    lines += ['', '## Agent findings / Agent 判断', '', 'Citation validation checks references, not semantic truth.', '']
    for claim in claims:
        lines += [f"### {md(claim['claim'])}", f"Status: {md(claim['status'])}", '', md(claim['rationale']), '',
                  'Evidence: ' + ', '.join(md(x) for x in claim['evidence_ids']), '',
                  'Counterevidence: ' + md('; '.join(claim['counterevidence']) or 'None identified; not proof of absence'),
                  'Counterevidence IDs: ' + ', '.join(md(x) for x in claim.get('counterevidence_ids', [])),
                  'Limitations: ' + md('; '.join(claim['limitations'])), '']
    lines += ['## Evidence index / 证据索引', '']
    for item in bundle['evidence']:
        lines += [f"- **{item['id']}** {md(item['kind'])} — [GitHub source]({safe_url(item['url'])})",
                  f"  - Completeness: {md(json.dumps(item['completeness'], ensure_ascii=False))}"]
    markdown = '\n'.join(lines) + '\n'
    esc = lambda value: html.escape(str(value), quote=True)
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><title>GitHub Evidence Lens</title><style>body{max-width:1050px;margin:2rem auto;padding:1rem;font-family:system-ui;color:#182234;background:#f5f7fa}pre{white-space:pre-wrap;overflow-wrap:anywhere}article,section{background:white;border:1px solid #d7deea;border-radius:12px;padding:1rem;margin:1rem 0}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:.5rem;border-bottom:1px solid #dde}a{color:#1751b5}.notice{border-left:4px solid #c68b16;padding:1rem}code{overflow-wrap:anywhere}</style><body><h1>GitHub Evidence Lens</h1>'
    page += f'<h2>{esc(subject)}</h2><p class="notice">{esc(reviewed)}<br>Public evidence, not a personal score. Low evidence is not negative evidence.</p><p>Source: {esc(bundle.get("source", "unknown"))}</p>'
    page += f'<section><h2>Machine inventory / 机器清单</h2><p>{len(ids)} evidence items · {len(bundle.get("errors", []))} collection errors</p><table><tr><th>Observed PR category</th><th>Count</th></tr>'
    for owner in ('external', 'self'):
        for state in ('merged', 'open', 'closed_unmerged'):
            key = owner + '_' + state
            page += f'<tr><td>{key}</td><td>{esc(bundle.get("counts", {}).get(key, "n/a"))}</td></tr>'
    page += '</table><p>Counts describe the observed public search subset, not lifetime activity. External ownership does not establish independent human approval.</p></section>'
    page += '<section><h2>Coverage / 覆盖与限制</h2>'
    for key in ('budget', 'selection', 'coverage', 'errors', 'limitations'):
        page += f'<details><summary>{key}</summary><pre>{esc(json.dumps(bundle.get(key, "n/a"), ensure_ascii=False, indent=2))}</pre></details>'
    page += '</section><section><h2>Agent findings / Agent 判断</h2><p>References validated, not semantic truth. Human review required.</p>'
    for claim in claims:
        page += f'<article><h3>{esc(claim["claim"])}</h3><p><strong>{esc(claim["status"])}</strong></p><p>{esc(claim["rationale"])}</p><p>Evidence: '
        for eid in claim['evidence_ids']:
            page += f'<a href="#{eid}">{eid}</a> '
        page += '</p><h4>Counterevidence</h4><ul>' + ''.join(f'<li>{esc(x)}</li>' for x in claim['counterevidence']) + '</ul>'
        for eid in claim.get('counterevidence_ids', []):
            page += f'<a href="#{eid}">{eid}</a> '
        page += '<h4>Limitations</h4><ul>' + ''.join(f'<li>{esc(x)}</li>' for x in claim['limitations']) + '</ul></article>'
    if not claims:
        page += '<p>No agent findings supplied. This is an evidence inventory, not an assessment.</p>'
    page += '</section><section><h2>Evidence / 证据</h2>'
    for item in bundle['evidence']:
        page += f'<article id="{item["id"]}"><h3>{esc(item["kind"])}</h3><code>{item["id"]}</code> · <a rel="noreferrer noopener" href="{safe_url(item["url"])}">GitHub source</a><p>Retrieved: {esc(item.get("retrieved_at", "unknown"))} · Head: {esc(item.get("head_sha") or "n/a")}</p><p>Completeness: {esc(json.dumps(item["completeness"]))}</p><details><summary>Sanitized raw evidence</summary><pre>{esc(json.dumps(item["content"], ensure_ascii=False, indent=2))}</pre></details></article>'
    page += '</section></body></html>'
    counts = bundle.get('counts', {})
    detailed = sum(e['kind'] == 'pr_detail' for e in bundle['evidence'])
    card_lines = ['GitHub Evidence Lens · ' + subject[:55],
                  'External merged/open/closed: ' + '/'.join(str(counts.get('external_' + s, 'n/a')) for s in ('merged', 'open', 'closed_unmerged')),
                  f'{detailed} PR details sampled | {len(claims)} agent findings | {len(bundle.get("errors", []))} errors',
                  reviewed, 'Public evidence only · No personal score', 'Read report for coverage, truncation and limitations']
    card = '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="300" viewBox="0 0 900 300" role="img"><title>Public evidence summary</title><rect width="900" height="300" rx="16" fill="#111827"/>'
    for index, line in enumerate(card_lines):
        card += f'<text x="28" y="{42 + index * 44}" fill="#f3f4f6" font-family="sans-serif" font-size="18">{html.escape(line, quote=True)}</text>'
    card += '</svg>\n'
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for name, content in [('report.md', markdown), ('report.html', page), ('card.svg', card)]:
        (out / name).write_text(content, encoding='utf-8')
    return {'evidence_items': len(ids), 'findings': len(claims), 'files': ['report.md', 'report.html', 'card.svg']}
