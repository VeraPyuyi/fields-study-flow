"""Small curated prerequisite DAG and numerical scheduling estimates (not deadlines)."""
import math
import re
from datetime import date
from fields_study_flow.concepts import concept_id, tokenize

GRAPH = {
    'math': ([], 8),
    'python': ([], 6),
    'machine learning': (['math', 'python'], 10),
    'deep learning': (['machine learning'], 10),
    'transformer': (['deep learning'], 8),
    'diffusion': (['deep learning'], 8),
    'llm': (['transformer'], 8),
}


def prerequisite_nodes(profile, resources=()):
    terms = tokenize(profile.goal)
    # A paper URL alone carries no topic. Use the supplied resource concepts,
    # including curated target-paper tags, without fetching paper contents.
    for resource in resources:
        for concept in resource.concepts + resource.prerequisites:
            terms.update(tokenize(concept))
    targets = [key for key in GRAPH if key in terms]
    if 'yolo' in terms or 'cnn' in terms:
        targets.append('deep learning')
    known = {concept_id(topic) for topic in profile.known_topics}
    nodes, seen, visiting = [], set(), []

    def visit(key):
        if key in visiting:
            raise ValueError('Prerequisite cycle: ' + ' -> '.join(visiting + [key]))
        if key not in GRAPH:
            raise ValueError(f'unknown prerequisite: {key}')
        if key in seen:
            return
        visiting.append(key)
        deps, hours = GRAPH[key]
        for dep in deps:
            visit(dep)
        visiting.pop()
        seen.add(key)
        skipped = key in known
        nodes.append({'id': key, 'depends_on': deps, 'estimated_hours': hours, 'status': 'skipped' if skipped else 'required', 'reason': 'Already known according to learner profile' if skipped else 'Prerequisite for target concepts'})
    for target in targets:
        visit(target)
    return nodes


def order_resources(profile, nodes, resources):
    """Stable concept-level topological order, shared by phases and schedule."""
    remaining = sorted(resources, key=lambda resource: (
        bool(resource.metadata.get('target_paper')),
        {'beginner': 0, 'intermediate': 1, 'advanced': 2}.get(resource.difficulty, 1),
    ))
    learned = {concept_id(topic) for topic in profile.known_topics}
    planned = {concept_id(node['id']) for node in nodes}
    provided = {concept_id(concept) for resource in resources for concept in resource.concepts}
    # Prefer concrete resource providers over a generic curated estimate.
    available = learned | (planned - provided)
    unknown = [f'{resource.title}: {dependency}' for resource in resources
               for dependency in resource.prerequisites
               if concept_id(dependency) not in available | provided]
    if unknown:
        raise ValueError('unknown prerequisite(s): ' + '; '.join(unknown))
    ordered = []
    while remaining:
        ready = next((resource for resource in remaining
                      if all(concept_id(dep) in available for dep in resource.prerequisites)), None)
        if ready is None:
            # Concrete providers are preferred, but may themselves require the
            # concept they teach. Curated foundations are already scheduled
            # before every resource, so use that independent coverage before
            # declaring a cycle. Never invent coverage for custom concepts.
            covered = {concept_id(dep) for resource in remaining for dep in resource.prerequisites}
            covered &= planned - available
            if covered:
                available.update(covered)
                continue
            blocked = '; '.join(f'{resource.title}: {", ".join(resource.prerequisites)}' for resource in remaining)
            raise ValueError('Resource dependency cycle: ' + blocked)
        remaining.remove(ready)
        ordered.append(ready)
        available.update(concept_id(concept) for concept in ready.concepts)
    return ordered


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
    uncertain = False
    for item in items:
        if item['hours'] is None:
            uncertain = True
        item['start_week'] = math.floor(total / profile.weekly_hours) + 1 if profile.weekly_hours and not uncertain else None
        total += item['hours'] or 0
        item['end_week'] = max(1, math.ceil(total / profile.weekly_hours)) if profile.weekly_hours and not uncertain else None
    weeks = math.ceil(total / profile.weekly_hours) if profile.weekly_hours and not unknown else None
    feasible = None
    available = None
    if profile.target_date and profile.weekly_hours:
        available = max(0, (date.fromisoformat(profile.target_date) - date.today()).days) / 7 * profile.weekly_hours
        feasible = False if total > available else None if unknown else True
    return {'available_hours': available, 'shortfall_hours': max(0, total - available) if available is not None else None, 'shortfall_is_lower_bound': bool(unknown), 'items': items, 'estimated_hours': None if unknown else total, 'known_estimated_hours': total, 'unknown_estimates': unknown, 'total_weeks': weeks, 'target_date': profile.target_date, 'deadline_feasible': feasible, 'note': 'Sequential study estimates; weeks after an unknown duration remain unknown. Known hours are a subtotal. Prerequisite and resource study may overlap.'}
