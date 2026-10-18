"""Public metadata adapters. No credentials, content scraping, or automatic redirects."""
from __future__ import annotations

import hashlib
import json
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

from fields_study_flow.models import Resource
from fields_study_flow.offline_catalog import offline_resources_for_goal


@dataclass
class Response:
    status: int
    body: bytes
    url: str


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def public_get(url, timeout):
    request = Request(url, headers={'User-Agent': 'fields-study-flow/0.1 (public metadata)', 'Accept': 'application/json, application/atom+xml'})
    try:
        with build_opener(NoRedirect).open(request, timeout=timeout) as response:
            return Response(response.status, response.read(2_000_001), response.url)
    except HTTPError as exc:
        return Response(exc.code, b'', url)


class SearchService:
    def __init__(self, cache_dir=None, transport=public_get, timeout=5, ttl=3600, min_interval=3):
        self.cache_dir = Path(cache_dir or os.environ.get('FIELDS_STUDY_FLOW_CACHE', Path.home() / '.cache' / 'fields-study-flow'))
        self.transport, self.timeout, self.ttl, self.min_interval = transport, timeout, ttl, min_interval
        self.last_request = 0.0

    def _fetch(self, url):
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache_dir / (key + '.json')
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if time.time() - data['timestamp'] < self.ttl:
                return data['resources'], 'cache'
        except (OSError, ValueError, KeyError):
            pass
        delay = self.min_interval - (time.monotonic() - self.last_request)
        if delay > 0:
            time.sleep(delay)
        self.last_request = time.monotonic()
        response = self.transport(url, self.timeout)
        if response.url != url:
            raise ValueError('redirect rejected')
        if response.status != 200:
            raise ValueError(f'HTTP {response.status}; no automatic retry')
        if len(response.body) > 2_000_000:
            raise ValueError('metadata response too large')
        resources = self._normalize(response.body, 'github' if 'api.github.com' in url else 'arxiv')
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'timestamp': time.time(), 'resources': resources}), encoding='utf-8')
        except OSError:
            pass
        return resources, 'live'

    def _normalize(self, body, source):
        now = datetime.now(timezone.utc).isoformat()
        output = []
        if source == 'github':
            payload = json.loads(body)
            items = payload.get('items', [payload])
            for item in items:
                name = item['full_name']
                # Always construct canonical public URLs rather than trusting response links.
                if len(name.split('/')) != 2 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._/' for c in name):
                    raise ValueError('invalid repository name')
                output.append(Resource(title=name, url='https://github.com/' + name, source='github', type='repository', language='en', concepts=item.get('topics', []), trust_score=0.7, metadata={'id': f"github:{item['id']}", 'retrieved_at': now, 'source': source, 'description': item.get('description'), 'code_language': item.get('language'), 'stars': item.get('stargazers_count', 0)}).to_dict())
        else:
            ns = {'a': 'http://www.w3.org/2005/Atom'}
            root = ET.fromstring(body)
            for entry in root.findall('a:entry', ns):
                identifier = entry.findtext('a:id', '', ns).rsplit('/abs/', 1)[-1]
                import re
                if not re.fullmatch(r'(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?', identifier):
                    raise ValueError('invalid arXiv id')
                output.append(Resource(title=' '.join(entry.findtext('a:title', '', ns).split()), url='https://arxiv.org/abs/' + identifier, source='arxiv', type='paper', language='en', difficulty='advanced', trust_score=0.85, metadata={'id': 'arxiv:' + identifier, 'retrieved_at': now, 'source': source, 'summary': entry.findtext('a:summary', '', ns)}).to_dict())
        return output

    def search(self, query, sources=None, filters=None, offline=False):
        filters = filters or {}
        selected = list(dict.fromkeys(sources or ['arxiv', 'github']))
        reasons, modes, resources = [], [], []
        if offline:
            resources = [r.to_dict() for r in offline_resources_for_goal(query)]
            if sources:
                from fields_study_flow.sources import SourceRegistry
                registry = SourceRegistry.default()
                allowed = set(sources)
                for source in sources:
                    registered = registry.sources.get(source)
                    if registered and registered.category == 'course':
                        allowed.add('course')
                resources = [r for r in resources if r['source'] in allowed]
            modes.append('offline')
            reasons.append('Explicit offline catalog; curated suggestions, not live query matches')
        else:
            for source in selected:
                if source not in {'arxiv', 'github'}:
                    reasons.append(f'{source}: adapter unavailable')
                    continue
                url = ('https://api.github.com/search/repositories?' + urlencode({'q': query, 'per_page': 10}) if source == 'github' else 'https://export.arxiv.org/api/query?' + urlencode({'search_query': 'all:' + query, 'max_results': 10}))
                try:
                    found, mode = self._fetch(url)
                    resources.extend(found)
                    modes.append(mode)
                except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
                    reasons.append(f'{source}: {type(exc).__name__}: {exc}')
        for field in ('type', 'language', 'difficulty'):
            if filters.get(field):
                resources = [r for r in resources if r[field] == filters[field]]
        return {'resources': resources, 'mode': ('offline' if offline else 'degraded' if reasons else modes[0] if len(set(modes)) == 1 else 'mixed'), 'degraded': reasons, 'source_modes': modes}

    def ingest(self, url):
        parsed = urlsplit(url)
        if parsed.scheme.lower() != 'https' or parsed.username or parsed.password or parsed.hostname not in {'github.com', 'arxiv.org'}:
            raise ValueError('only credential-free public HTTPS GitHub/arXiv metadata URLs are supported')
        parts = parsed.path.strip('/').split('/')
        if parsed.hostname == 'github.com' and len(parts) == 2 and all(parts):
            api = 'https://api.github.com/repos/' + '/'.join(quote(p, safe='') for p in parts)
        elif parsed.hostname == 'arxiv.org' and len(parts) >= 2 and parts[0] in {'abs', 'pdf'}:
            api = 'https://export.arxiv.org/api/query?' + urlencode({'id_list': '/'.join(parts[1:]).removesuffix('.pdf')})
        else:
            raise ValueError('unsupported public metadata URL')
        resources, mode = self._fetch(api)
        if not resources:
            raise ValueError('no public metadata returned')
        resources[0]['metadata']['retrieval_mode'] = mode
        return resources[0]
