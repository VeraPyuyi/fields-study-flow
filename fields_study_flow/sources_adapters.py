"""Public metadata adapters. No credentials, content scraping, or automatic redirects."""
from __future__ import annotations

import hashlib
import json
import os
import time
import tempfile
from threading import Lock
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


# Shared by every service instance in this process, independently per API host.
_SOURCE_LOCKS = {'api.github.com': Lock(), 'export.arxiv.org': Lock()}
_LAST_REQUEST: dict[str, float] = {}


class SearchService:
    def __init__(self, cache_dir=None, transport=public_get, timeout=5, ttl=3600, min_interval=3):
        self.cache_dir = Path(cache_dir or os.environ.get('FIELDS_STUDY_FLOW_CACHE', Path.home() / '.cache' / 'fields-study-flow'))
        self.transport, self.timeout, self.ttl, self.min_interval = transport, timeout, ttl, min_interval

    def _fetch(self, url):
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache_dir / (key + '.json')
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not isinstance(data.get('timestamp'), (int, float)):
                raise ValueError('invalid cache envelope')
            cached = data.get('resources')
            if not isinstance(cached, list):
                raise ValueError('invalid cached resources')
            for item in cached:
                if not isinstance(item, dict):
                    raise ValueError('cached resource must be an object')
                resource = Resource(**item)
                if (not all(isinstance(getattr(resource, field), str) for field in ('title', 'url', 'source', 'type', 'language', 'difficulty'))
                        or not isinstance(resource.concepts, list)
                        or not all(isinstance(c, str) for c in resource.concepts)
                        or not isinstance(resource.metadata, dict)):
                    raise ValueError('invalid cached resource structure')
            if time.time() - data['timestamp'] < self.ttl:
                return cached, 'cache'
        except (OSError, ValueError, KeyError, TypeError):
            pass
        host = urlsplit(url).hostname
        with _SOURCE_LOCKS[host]:
            delay = self.min_interval - (time.monotonic() - _LAST_REQUEST.get(host, float('-inf')))
            if delay > 0:
                time.sleep(delay)
            _LAST_REQUEST[host] = time.monotonic()
            response = self.transport(url, self.timeout)
        if response.url != url:
            raise ValueError('redirect rejected')
        if response.status != 200:
            raise ValueError(f'HTTP {response.status}; no automatic retry')
        if len(response.body) > 2_000_000:
            raise ValueError('metadata response too large')
        resources = self._normalize(response.body, 'github' if 'api.github.com' in url else 'arxiv')
        temporary = None
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.cache_dir, suffix='.tmp', delete=False) as handle:
                temporary = Path(handle.name)
                json.dump({'timestamp': time.time(), 'resources': resources}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError:
            pass
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return resources, 'live'

    def _normalize(self, body, source):
        try:
            return self._parse_metadata(body, source)
        except (ValueError, TypeError, KeyError, AttributeError, ET.ParseError) as exc:
            kind = 'JSON' if source == 'github' else 'XML'
            raise ValueError(f'{source} {kind} metadata: {exc}') from exc

    def _parse_metadata(self, body, source):
        now = datetime.now(timezone.utc).isoformat()
        output = []
        if source == 'github':
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError('response must be an object')
            items = payload.get('items', [payload])
            if not isinstance(items, list):
                raise ValueError('items must be an array')
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError('repository must be an object')
                name = item.get('full_name')
                # Always construct canonical public URLs rather than trusting response links.
                if (not isinstance(name, str) or len(name.split('/')) != 2 or not all(name.split('/'))
                        or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._/' for c in name)):
                    raise ValueError('invalid repository full_name')
                if type(item.get('id')) is not int or item['id'] <= 0:
                    raise ValueError('repository id must be a positive integer')
                topics = item.get('topics', [])
                if not isinstance(topics, list) or not all(isinstance(topic, str) for topic in topics):
                    raise ValueError('topics must be an array of strings')
                if type(item.get('stargazers_count', 0)) is not int or item.get('stargazers_count', 0) < 0:
                    raise ValueError('stargazers_count must be a nonnegative integer')
                for field in ('description', 'language'):
                    if item.get(field) is not None and not isinstance(item[field], str):
                        raise ValueError(f'{field} must be text or null')
                output.append(Resource(title=name, url='https://github.com/' + name, source='github', type='repository', language='en', concepts=item.get('topics', []), trust_score=0.7, metadata={'id': f"github:{item['id']}", 'retrieved_at': now, 'source': source, 'description': item.get('description'), 'code_language': item.get('language'), 'stars': item.get('stargazers_count', 0)}).to_dict())
        else:
            ns = {'a': 'http://www.w3.org/2005/Atom'}
            root = ET.fromstring(body)
            if root.tag != '{http://www.w3.org/2005/Atom}feed':
                raise ValueError('expected an Atom feed')
            for entry in root.findall('a:entry', ns):
                if not entry.findtext('a:title', '', ns).strip():
                    raise ValueError('entry title is required')
                identifier = entry.findtext('a:id', '', ns).rsplit('/abs/', 1)[-1]
                import re
                if not re.fullmatch(r'(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?', identifier):
                    raise ValueError('invalid arXiv id')
                from fields_study_flow.concepts import tokenize
                from fields_study_flow.prerequisites import GRAPH
                identifier = re.sub(r'v\d+$', '', identifier)
                title = ' '.join(entry.findtext('a:title', '', ns).split())
                summary = ' '.join(entry.findtext('a:summary', '', ns).split())
                published = entry.findtext('a:published', '', ns)
                metadata = {'id': 'arxiv:' + identifier, 'retrieved_at': now, 'source': source,
                            'summary': summary, 'authors': [' '.join(a.findtext('a:name', '', ns).split()) for a in entry.findall('a:author', ns)],
                            'year': int(published[:4]) if re.match(r'^\d{4}-', published) else None,
                            'categories': sorted({c.get('term') for c in entry.findall('a:category', ns) if c.get('term')})}
                if not summary:
                    metadata.update(degraded='Abstract unavailable; title-only concept matching', next_action='Supply an abstract and concept tags, or use an arXiv metadata URL.')
                concepts = sorted(set(GRAPH) & tokenize(title + ' ' + summary))
                output.append(Resource(title=title, url='https://arxiv.org/abs/' + identifier, source='arxiv', type='paper', language='en', difficulty='advanced', concepts=concepts, trust_score=0.85, metadata=metadata).to_dict())
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
                pages = max(1, min(10, int(filters.get('pages', 1))))
                size = max(1, min(100, int(filters.get('page_size', 10))))
                for page in range(pages):
                    url = ('https://api.github.com/search/repositories?' + urlencode({'q': query, 'per_page': size, 'page': page + 1, 'sort': 'updated', 'order': 'asc'}) if source == 'github' else 'https://export.arxiv.org/api/query?' + urlencode({'search_query': 'all:' + query, 'max_results': size, 'start': page * size, 'sortBy': 'submittedDate', 'sortOrder': 'ascending'}))
                    try:
                        found, mode = self._fetch(url)
                        resources.extend(found)
                        modes.append(mode)
                        if len(found) < size:
                            break
                    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
                        reasons.append(f'{source}: {type(exc).__name__}: {exc}')
                        break
        unique = {}
        for resource in resources:
            unique.setdefault(resource['metadata'].get('id', resource['url']), resource)
        resources = list(unique.values())
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
        if parsed.hostname == 'arxiv.org':
            resources[0]['metadata']['target_paper'] = True
        resources[0]['metadata']['retrieval_mode'] = mode
        return resources[0]
