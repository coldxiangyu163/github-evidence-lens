"""Bounded, read-only public evidence collector (Python standard library)."""
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlencode

USER = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
REPO = rf"{USER}/[A-Za-z0-9_.-]{{1,100}}"
ENDPOINT = re.compile(rf"(?:users/{USER}(?:/repos)?|search/issues|repos/{REPO}(?:/pulls/[1-9][0-9]*(?:/(?:files|reviews|comments))?|/issues/[1-9][0-9]*/comments|/commits/[a-fA-F0-9]{{40}}/check-runs)?)\Z")


def username(value):
    if not re.fullmatch(USER, value) or '--' in value:
        raise ValueError('Invalid GitHub username (exact input required)')
    return value


def reference(value):
    match = re.fullmatch(rf'({REPO})#([1-9][0-9]*)', value)
    if not match or match[1].split('/')[1] in ('.', '..'):
        raise ValueError('Expected exact OWNER/REPO#N')
    username(match[1].split('/')[0])
    return match[1], int(match[2])


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def actor(value):
    return {k: value.get(k) for k in ('login', 'type') if k in value} if isinstance(value, dict) else {}


def sanitize(value):

    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items() if k.lower() not in {'email', 'gravatar_id', 'token', 'phone', 'blog', 'location', 'company', 'twitter_username'}}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'(?i)[\w.+-]+@[\w.-]+\.[a-z]{2,}', '[REDACTED_EMAIL]', value)
        value = re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{16,})\b', '[REDACTED_SECRET]', value)
        value = re.sub(r'(?i)(?:https?://)[^\s/]+:[^\s/@]+@', 'https://[REDACTED]@', value)
        value = re.sub(r'(?i)(?:phone|tel|mobile|wechat|telegram|contact)\s*[:=]\s*\S+', '[REDACTED_CONTACT]', value)
        return ''.join(c for c in value if c in '\n\t' or ord(c) >= 32)
    return value


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.evidence-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class APIError(Exception):
    pass


class GhAPI:
    """Never shell-executes, never accepts a URL or arbitrary API endpoint."""
    def __init__(self, max_bytes=2_000_000, timeout=45):
        self.max_bytes, self.timeout = max_bytes, timeout

    def get(self, endpoint, params=None):
        if not ENDPOINT.fullmatch(endpoint):
            raise APIError('Endpoint not allowed')
        query = '?' + urlencode(params) if params else ''
        args = ['gh', 'api', '--hostname', 'github.com', '--method', 'GET', '--include',
                '-H', 'Accept: application/vnd.github+json', '-H', 'X-GitHub-Api-Version: 2022-11-28', endpoint + query]
        env = dict(os.environ, GH_PAGER='cat', GH_PROMPT_DISABLED='1', GH_HOST='github.com')
        try:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        except OSError as exc:
            raise APIError('gh unavailable') from exc
        assert proc.stdout is not None
        timer = threading.Timer(self.timeout, proc.kill)
        timer.start()
        try:
            raw = proc.stdout.read(self.max_bytes + 1)
            if len(raw) > self.max_bytes:
                proc.kill()
                raise APIError('Response byte budget exceeded; response discarded (truncated)')
            code = proc.wait()
        finally:
            timer.cancel()
            proc.stdout.close()
            if proc.poll() is None:
                proc.kill()
            proc.wait()
        text = raw.decode('utf-8', errors='replace').replace('\r\n', '\n')
        headers, sep, body = text.partition('\n\n')
        status = re.search(r'HTTP/\S+\s+(\d+)', headers)
        if not sep or not status or code or int(status[1]) != 200:
            limited = 'rate limit' if re.search(r'(?im)^x-ratelimit-remaining:\s*0\s*$', headers) else 'HTTP/API error or timeout'
            raise APIError(f'{limited}; status={status[1] if status else "unavailable"}')
        # Do not store response headers (they can contain authentication metadata).
        try:
            return json.loads(body)
        except ValueError as exc:
            raise APIError('Invalid API JSON') from exc


class Collector:
    def __init__(self, api=None, max_pages=10, max_prs=100, sample_prs=6):
        if not 1 <= max_pages <= 100 or not 1 <= max_prs <= 1000 or not 0 <= sample_prs <= 100:
            raise ValueError('Budgets: pages 1..100, PRs 1..1000, sample 0..100')
        self.api = api or GhAPI()
        self.max_pages, self.max_prs, self.sample_prs = max_pages, max_prs, sample_prs
        self.bundle = {'schema_version': '0.1', 'retrieved_at': now(), 'source': 'live-public-github',
                       'evidence': [], 'errors': [], 'coverage': {}, 'budget': {'max_pages_per_endpoint': max_pages, 'max_prs': max_prs, 'sample_prs': sample_prs},
                       'limitations': ['Public evidence only; absence is not negative evidence.', 'Search ceiling: 1000 results; search index may lag.', 'Patch omission, redaction and sampling prevent complete code review.']}
        self.public = set()

    def request(self, endpoint, params=None):
        try:
            return self.api.get(endpoint, params)
        except (APIError, OSError, ValueError) as exc:
            # Never persist arbitrary exception text, which may contain secrets.
            message = str(exc) if isinstance(exc, APIError) else type(exc).__name__
            self.bundle['errors'].append({'endpoint': endpoint, 'error': sanitize(message), 'retrieved_at': now()})
            return None

    def add(self, kind, url, content, repo=None, pr=None, sha=None, flags=None):
        identity = f'{kind}|{url}|{pr or ""}|{sha or ""}'
        item = {'id': 'ev_' + hashlib.sha256(identity.encode()).hexdigest()[:20], 'kind': kind, 'url': url,
                'retrieved_at': now(), 'repo': repo, 'pr': pr, 'head_sha': sha, 'content': sanitize(content),
                'completeness': {'truncated': False, 'errors': False, **(flags or {})}}
        self.bundle['evidence'] = [e for e in self.bundle['evidence'] if e['id'] != item['id']]
        self.bundle['evidence'].append(item)
        return item

    def verify(self, repo):
        if repo in self.public:
            return True
        data = self.request('repos/' + repo)
        if not isinstance(data, dict) or data.get('private') is not False or data.get('visibility') != 'public' or data.get('full_name', '').lower() != repo.lower():
            self.bundle['errors'].append({'endpoint': 'repos/' + repo, 'error': 'Public visibility verification failed; repository excluded', 'retrieved_at': now()})
            return False
        self.public.add(repo)
        self.add('repository', 'https://github.com/' + repo,
                 {k: data.get(k) for k in ('full_name', 'private', 'visibility', 'fork', 'archived', 'language', 'stargazers_count')}, repo)
        return True

    def pages(self, endpoint, key=None, limit=None, params=None):
        result, total, incomplete, failed, ended = [], None, False, False, False
        page = 0
        for page in range(1, self.max_pages + 1):
            data = self.request(endpoint, {**(params or {}), 'per_page': 100, 'page': page})
            rows = data.get(key) if isinstance(data, dict) and key else data
            if not isinstance(rows, list):
                failed = True
                if data is not None:
                    self.bundle['errors'].append({'endpoint': endpoint, 'error': 'Unexpected collection shape', 'retrieved_at': now()})
                break
            if isinstance(data, dict):
                total = data.get('total_count', total)
                incomplete |= data.get('incomplete_results', False) is True
            result.extend(rows)
            ended = len(rows) < 100 or (isinstance(total, int) and len(result) >= total)
            if ended or (limit and len(result) >= limit):
                break
        clipped = limit is not None and len(result) > limit
        result = result[:limit] if limit else result
        flags = {'truncated': clipped or not ended or incomplete, 'errors': failed, 'incomplete_results': incomplete,
                 'observed': len(result), 'total': total, 'pages': page}
        self.bundle['coverage'][endpoint] = flags
        return result, flags

    @staticmethod
    def group(row, user):
        ownership = 'self' if row['repo'].split('/')[0].lower() == user.lower() else 'external'
        state = 'merged' if row['merged'] else ('open' if row['state'] == 'open' else 'closed_unmerged')
        return ownership + '_' + state

    def collect(self, user):
        username(user)
        self.bundle['subject'] = user
        profile = self.request('users/' + user)
        if isinstance(profile, dict):
            self.add('profile', 'https://github.com/' + user, {k: profile.get(k) for k in ('login', 'type', 'public_repos', 'created_at')})
        repos, flags = self.pages('users/' + user + '/repos', params={'type': 'owner', 'sort': 'full_name'})
        for repo in repos:
            name = repo.get('full_name', '')
            if re.fullmatch(REPO, name) and repo.get('private') is False:
                self.verify(name)
        rows, flags = self.pages('search/issues', 'items', self.max_prs,
                                 {'q': f'is:pr is:public author:{user}', 'sort': 'created', 'order': 'desc'})
        candidates, seen = [], set()
        for row in rows:
            match = re.fullmatch(rf'https://github.com/({REPO})/pull/([1-9][0-9]*)', row.get('html_url', ''))
            if not match or row['html_url'] in seen:
                continue
            repo, number = match[1], int(match[2])
            if not self.verify(repo):
                continue
            seen.add(row['html_url'])
            pr_meta = row.get('pull_request') or {}
            state = row.get('state')
            if 'merged_at' in pr_meta:
                merged = bool(pr_meta['merged_at'])
            else:
                endpoint = f'repos/{repo}/pulls/{number}'
                detail = self.request(endpoint)
                base = detail.get('base', {}).get('repo', {}) if isinstance(detail, dict) else {}
                if (not isinstance(detail, dict) or type(detail.get('merged')) is not bool
                        or base.get('private') is not False
                        or base.get('visibility') not in (None, 'public')
                        or base.get('full_name', '').lower() != repo.lower()):
                    self.bundle['errors'].append({'endpoint': endpoint, 'error': 'Merge status unavailable or public base mismatch; PR excluded from classified counts', 'retrieved_at': now()})
                    continue
                merged, state = detail['merged'], detail.get('state')
            if state not in ('open', 'closed'):
                self.bundle['errors'].append({'endpoint': f'repos/{repo}/pulls/{number}', 'error': 'Unknown PR state; excluded from classified counts', 'retrieved_at': now()})
                continue
            candidate = {'repo': repo, 'number': number, 'title': row.get('title', ''), 'state': state,
                         'merged': merged, 'url': row['html_url']}
            candidate['group'] = self.group(candidate, user)
            candidates.append(candidate)
            self.add('pr_inventory', candidate['url'], candidate, repo, number, flags=flags)
        groups = {f'{owner}_{state}': [] for owner in ('external', 'self') for state in ('merged', 'open', 'closed_unmerged')}
        for candidate in candidates:
            groups[candidate['group']].append(candidate)
        self.bundle['counts'] = {k: len(v) for k, v in groups.items()}
        self.bundle['coverage']['search/issues']['unique_public_observed'] = len(candidates)
        selected = []
        while len(selected) < self.sample_prs and any(groups.values()):
            for group in groups.values():
                if group and len(selected) < self.sample_prs:
                    selected.append(group.pop(0))
        self.bundle['selection'] = {'method': 'Round-robin external merged/open/closed-unmerged, then self equivalents; search newest-created order.', 'selected': [c['url'] for c in selected], 'candidate_count': len(candidates)}
        for candidate in selected:
            self.inspect(f"{candidate['repo']}#{candidate['number']}")
        return self.bundle

    def inspect(self, target):
        repo, number = reference(target)
        if not self.verify(repo):
            return self.bundle
        endpoint = f'repos/{repo}/pulls/{number}'
        url = f'https://github.com/{repo}/pull/{number}'
        data = self.request(endpoint)
        if not isinstance(data, dict):
            return self.bundle
        # A public base PR can refer to a private/deleted head. Never visit that head repository.
        base = data.get('base', {}).get('repo', {})
        if base.get('private') is not False or base.get('visibility') not in (None, 'public') or base.get('full_name', '').lower() != repo.lower():
            self.bundle['errors'].append({'endpoint': endpoint, 'error': 'PR base public identity mismatch', 'retrieved_at': now()})
            return self.bundle
        sha = data.get('head', {}).get('sha')
        if not isinstance(sha, str) or not re.fullmatch('[a-fA-F0-9]{40}', sha):
            sha = None
        self.add('pr_detail', url, {**{k: data.get(k) for k in ('number', 'title', 'body', 'state', 'merged', 'merged_at', 'draft', 'additions', 'deletions', 'changed_files', 'author_association')}, 'user': actor(data.get('user'))}, repo, number, sha)
        for kind, path, key, fields in [
            ('files', endpoint + '/files', None, ('filename', 'status', 'additions', 'deletions', 'patch')),
            ('reviews', endpoint + '/reviews', None, ('id', 'body', 'state', 'submitted_at', 'commit_id')),
            ('review_comments', endpoint + '/comments', None, ('id', 'body', 'path', 'line', 'diff_hunk', 'commit_id')),
            ('discussion', f'repos/{repo}/issues/{number}/comments', None, ('id', 'body', 'created_at')),
        ]:
            rows, flags = self.pages(path, key)
            if kind == 'files':
                flags = {**flags, 'patch_missing': any('patch' not in r for r in rows),
                         'truncated': flags['truncated'] or len(rows) < (data.get('changed_files') or 0), 'patch_completeness_unknown': True}
            content = [{**{k: r.get(k) for k in fields if k in r}, **({'user': actor(r.get('user')), 'author_association': r.get('author_association'), 'html_url': r.get('html_url')} if kind != 'files' else {})} for r in rows]
            self.add(kind, url, content, repo, number, sha, flags)
        if sha:
            rows, flags = self.pages(f'repos/{repo}/commits/{sha}/check-runs', 'check_runs')
            self.add('checks', f'https://github.com/{repo}/commit/{sha}/checks',
                     [{k: r.get(k) for k in ('id', 'name', 'status', 'conclusion', 'started_at', 'completed_at')} for r in rows], repo, number, sha, flags)
        return self.bundle
