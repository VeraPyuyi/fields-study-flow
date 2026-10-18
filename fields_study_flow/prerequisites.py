"""Small curated prerequisite DAG and numerical scheduling estimates (not deadlines)."""
import math
import re
from datetime import date
from fields_study_flow.ranking import _tokenize

GRAPH = {
    'math': ([], 8),
    'python': ([], 6),
    'machine learning': (['math', 'python'], 10),
    'deep learning': (['machine learning'], 10),
    'transformer': (['deep learning'], 8),
    'diffusion': (['deep learning'], 8),
    'llm': (['transformer'], 8),
}


def prerequisite_nodes(profile):
    terms = _tokenize(profile.goal)
    targets = [key for key in GRAPH if key in terms or set(key.split()) <= terms]
    if 'yolo' in terms or 'cnn' in terms:
        targets.append('deep learning')
    known = set()
    for topic in profile.known_topics:
        known.update(_tokenize(topic))
        known.add(topic.lower())
    nodes, seen = [], set()
    def visit(key):
        if key in seen:
            return
        seen.add(key)
        deps, hours = GRAPH[key]
        for dep in deps:
            visit(dep)
        skipped = key in known or set(key.split()) <= known
        nodes.append({'id': key, 'depends_on': deps, 'estimated_hours': hours, 'status': 'skipped' if skipped else 'required', 'reason': 'Already known according to learner profile' if skipped else 'Prerequisite for target concepts'})
    for target in targets:
        visit(target)
    return nodes


def schedule(profile, nodes, resources):
    items, unknown, total = [], [], 0.0
    for node in nodes:
        if node['status'] == 'skipped':
            continue
        items.append({'id': node['id'], 'hours': node['estimated_hours'], 'kind': 'prerequisite'})
    for resource in resources:
        match = re.fullmatch(r'(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?h', resource.estimated_time)
        hours = float(match.group(2) or match.group(1)) if match else None
        if hours is None:
            unknown.append(resource.url)
        items.append({'id': resource.url, 'hours': hours, 'kind': 'resource'})
    for item in items:
        if item['hours'] is None:
            item.update(start_week=None, end_week=None)
            continue
        item['start_week'] = math.floor(total / profile.weekly_hours) + 1 if profile.weekly_hours else None
        total += item['hours']
        item['end_week'] = max(1, math.ceil(total / profile.weekly_hours)) if profile.weekly_hours else None
    weeks = math.ceil(total / profile.weekly_hours) if profile.weekly_hours else None
    feasible = None
    if profile.target_date and profile.weekly_hours:
        available = max(0, (date.fromisoformat(profile.target_date) - date.today()).days) / 7 * profile.weekly_hours
        feasible = False if total > available else None if unknown else True
    return {'items': items, 'estimated_hours': total, 'unknown_estimates': unknown, 'total_weeks': weeks, 'target_date': profile.target_date, 'deadline_feasible': feasible, 'note': 'Estimates exclude unknown durations; prerequisite and resource study may overlap.'}
