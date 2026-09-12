from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from pathlib import Path

from .crossover_experiment import audit_p3_leakage
from .episode_log import EpisodeLog
from .item_calibration import audit_candidate_structure
from .measurement import make_unified_diff, measure_staleness
from .models import (
    ConflictEpisode,
    RecoveryAction,
    StaleDependency,
)
from .payloads import PayloadRenderer
from .validation import validate_dependencies, validate_revision


@dataclass(frozen=True)
class ScenarioFamily:
    name: str
    symbol: str
    task: str
    base: str
    proposed: str
    adapt_current: str
    abandon_current: str
    escalate_current: str
    behavior_check: str
    dependency_check: str

    @property
    def file_path(self) -> str:
        return f"{self.name}.py"


SCENARIO_FAMILIES = (
    ScenarioFamily(
        "email_normalization",
        "normalize_email",
        "Lowercase normalized email addresses while preserving text type validation.",
        "def normalize_email(value):\n    if not isinstance(value, str):\n        raise TypeError('email must be text')\n    return value.strip()\n",
        "def normalize_email(value):\n    if not isinstance(value, str):\n        raise TypeError('email must be text')\n    return value.strip().lower()\n",
        "def normalize_email(value):\n    if not isinstance(value, str):\n        raise TypeError('email must be text')\n    if not value.strip():\n        raise ValueError('email is empty')\n    return value.strip()\n",
        "def normalize_email(value):\n    if not isinstance(value, str):\n        raise TypeError('email must be text')\n    return value.strip().casefold()\n",
        "def normalize_email(value):\n    return str(value).strip().lower()\n",
        "assert normalize_email(' A@EXAMPLE.COM ') == 'a@example.com'\ntry:\n    normalize_email(3)\nexcept TypeError:\n    pass\nelse:\n    raise AssertionError('type validation lost')",
        "try:\n    normalize_email(3)\nexcept TypeError:\n    pass\nelse:\n    raise AssertionError('type validation lost')",
    ),
    ScenarioFamily(
        "label_rendering",
        "render_label",
        "Strip converted label values while preserving their optional prefix.",
        "def render_label(value, prefix=''):\n    return prefix + str(value)\n",
        "def render_label(value, prefix=''):\n    return prefix + str(value).strip()\n",
        "def render_label(value, prefix='', suffix=''):\n    return prefix + str(value) + suffix\n",
        "def render_label(value, prefix='', suffix=''):\n    combined = str(value).strip() + prefix\n    if prefix:\n        combined = combined[-len(prefix):] + combined[:-len(prefix)]\n    return combined + suffix\n",
        "def render_label(value, prefix=''):\n    return str(value).strip()\n",
        "assert render_label(' x ', prefix='>') == '>x'",
        "assert render_label('x', prefix='>') == '>x'",
    ),
    ScenarioFamily(
        "cache_configuration",
        "build_cache",
        "Add TTL configuration while preserving cache capacity and item storage.",
        "def build_cache(max_size):\n    return {'max_size': max_size, 'items': {}}\n",
        "def build_cache(max_size, ttl=60):\n    return {'max_size': max_size, 'ttl': ttl, 'items': {}}\n",
        "def build_cache(max_size):\n    return {'max_size': max_size, 'items': {}, 'hits': 0}\n",
        "def build_cache(max_size, ttl=60):\n    fields = ('items', 'ttl', 'max_size', 'hits')\n    values = ({}, ttl, max_size, 0)\n    pairs = list(zip(fields, values))\n    pairs.reverse()\n    return dict(reversed(pairs))\n",
        "def build_cache(max_size, ttl=60):\n    return {'ttl': ttl, 'items': {}}\n",
        "cache = build_cache(3, ttl=7)\nassert cache['max_size'] == 3 and cache['ttl'] == 7 and cache['items'] == {}",
        "cache = build_cache(3)\nassert cache['max_size'] == 3 and cache['items'] == {}",
    ),
    ScenarioFamily(
        "scope_authorization",
        "authorize",
        "Record successful authorization checks while preserving mandatory scope enforcement.",
        "def authorize(scopes, scope):\n    if scope not in scopes:\n        raise PermissionError(scope)\n    return True\n",
        "def authorize(scopes, scope, audit=None):\n    if scope not in scopes:\n        raise PermissionError(scope)\n    if audit is not None:\n        audit.append(scope)\n    return True\n",
        "def authorize(scopes, scope):\n    scope = scope.strip()\n    if scope not in scopes:\n        raise PermissionError(scope)\n    return True\n",
        "def authorize(scopes, scope, audit=None):\n    allowed = scope in scopes\n    if not allowed:\n        raise PermissionError(scope)\n    if audit is not None:\n        audit.append(scope)\n    return allowed\n",
        "def authorize(scopes, scope, audit=None):\n    if audit is not None:\n        audit.append(scope)\n    return True\n",
        "audit = []\nassert authorize({'read'}, 'read', audit) is True\nassert audit == ['read']\ntry:\n    authorize({'read'}, 'write', audit)\nexcept PermissionError:\n    pass\nelse:\n    raise AssertionError('scope enforcement lost')",
        "try:\n    authorize({'read'}, 'write')\nexcept PermissionError:\n    pass\nelse:\n    raise AssertionError('scope enforcement lost')",
    ),
    ScenarioFamily(
        "versioned_commit",
        "commit",
        "Accept a retry budget while preserving optimistic version rejection.",
        "def commit(store, expected_version, value):\n    if store['version'] != expected_version:\n        raise RuntimeError('stale')\n    store['values'].append(value)\n",
        "def commit(store, expected_version, value, retries=2):\n    for attempt in range(retries + 1):\n        if store['version'] == expected_version:\n            store['values'].append(value)\n            return\n    raise RuntimeError('stale')\n",
        "def commit(store, expected_version, value, logger=None):\n    if store['version'] != expected_version:\n        raise RuntimeError('stale')\n    store['values'].append(value)\n    if logger is not None:\n        logger.append('committed')\n",
        "def commit(store, expected_version, value, retries=2):\n    attempts = retries + 1\n    while attempts:\n        if store['version'] == expected_version:\n            store['values'].append(value)\n            return\n        attempts -= 1\n    raise RuntimeError('stale')\n",
        "def commit(store, expected_version, value, retries=2):\n    store['values'].append(value)\n",
        "store = {'version': 2, 'values': []}\ncommit(store, 2, 'x', retries=1)\nassert store['values'] == ['x']\nstale = {'version': 3, 'values': []}\ntry:\n    commit(stale, 2, 'x', retries=1)\nexcept RuntimeError:\n    pass\nelse:\n    raise AssertionError('version rejection lost')\nassert stale['values'] == []",
        "stale = {'version': 3, 'values': []}\ntry:\n    commit(stale, 2, 'x')\nexcept RuntimeError:\n    pass\nelse:\n    raise AssertionError('version rejection lost')\nassert stale['values'] == []",
    ),
    ScenarioFamily(
        "stable_serialization",
        "dumps",
        "Serialize mappings in deterministic key order while retaining mapping validation.",
        "def dumps(value):\n    if not isinstance(value, dict):\n        raise TypeError('mapping required')\n    return ','.join(str(key) + '=' + str(item) for key, item in value.items())\n",
        "def dumps(value):\n    if not isinstance(value, dict):\n        raise TypeError('mapping required')\n    return ','.join(str(key) + '=' + str(value[key]) for key in sorted(value))\n",
        "def dumps(value):\n    if not isinstance(value, dict):\n        raise TypeError('mapping required')\n    if not value:\n        return ''\n    return ','.join(str(key) + '=' + str(item) for key, item in value.items())\n",
        "def dumps(value):\n    if not isinstance(value, dict):\n        raise TypeError('mapping required')\n    parts = [str(key) + '=' + str(value[key]) for key in value]\n    parts.sort()\n    return ','.join(parts[::-1][::-1])\n",
        "def dumps(value):\n    return ','.join(str(item) for item in value)\n",
        "assert dumps({'b': 1, 'a': 2}) == 'a=2,b=1'\ntry:\n    dumps(['a'])\nexcept TypeError:\n    pass\nelse:\n    raise AssertionError('mapping validation lost')",
        "try:\n    dumps(['a'])\nexcept TypeError:\n    pass\nelse:\n    raise AssertionError('mapping validation lost')",
    ),
    ScenarioFamily(
        "ordered_deduplication",
        "unique",
        "Preserve first-seen order while deduplicating validated input.",
        "def unique(items):\n    if items is None:\n        raise TypeError('items required')\n    return list(set(items))\n",
        "def unique(items):\n    if items is None:\n        raise TypeError('items required')\n    return list(dict.fromkeys(items))\n",
        "def unique(items):\n    if items is None:\n        raise TypeError('items required')\n    return sorted(set(items))\n",
        "def unique(items, reverse=False):\n    result = sorted(set(items), key=lambda item: items.index(item)) if items is not None else None\n    if result is None:\n        raise TypeError('items required')\n    return result[::-1] if reverse else result\n",
        "def unique(items):\n    if items is None:\n        return []\n    return list(dict.fromkeys(items))\n",
        "assert unique(['b', 'a', 'b']) == ['b', 'a']\ntry:\n    unique(None)\nexcept TypeError:\n    pass\nelse:\n    raise AssertionError('missing-input validation lost')",
        "try:\n    unique(None)\nexcept TypeError:\n    pass\nelse:\n    raise AssertionError('missing-input validation lost')",
    ),
    ScenarioFamily(
        "page_window",
        "page",
        "Add an offset to bounded pagination while preserving negative-limit clamping.",
        "def page(items, limit):\n    limit = max(0, limit)\n    return items[:limit]\n",
        "def page(items, limit, offset=0):\n    limit = max(0, limit)\n    return items[offset:offset + limit]\n",
        "def page(items, limit, strict=False):\n    limit = max(0, limit)\n    if strict and limit == 0:\n        raise ValueError('empty page')\n    return items[:limit]\n",
        "def page(items, limit, offset=0, from_end=False):\n    if from_end:\n        offset = len(items) - offset - max(0, limit)\n    return items[offset:][:max(0, limit)]\n",
        "def page(items, limit, offset=0):\n    values = list(items)\n    values.reverse()\n    return values[offset:offset + limit]\n",
        "values = list(range(8))\nassert page(values, 3, offset=2) == [2, 3, 4]\nassert page(values, -2, offset=2) == []",
        "values = list(range(5))\nassert page(values, 2) == [0, 1]\nassert page(values, -1) == []",
    ),
    ScenarioFamily(
        "bounded_score",
        "clamp_score",
        "Support custom score bounds while preserving default 0-to-100 clamping.",
        "def clamp_score(value):\n    return max(0, min(100, value))\n",
        "def clamp_score(value, low=0, high=100):\n    return max(low, min(high, value))\n",
        "def clamp_score(value, digits=None):\n    result = max(0, min(100, value))\n    return round(result, digits) if digits is not None else result\n",
        "def clamp_score(value, low=0, high=100, strict=False):\n    if strict and low > high:\n        raise ValueError('invalid bounds')\n    return low + max(0, min(high - low, value - low))\n",
        "def clamp_score(value, low=0, high=100):\n    return value\n",
        "assert clamp_score(12, low=20, high=30) == 20\nassert clamp_score(40, low=20, high=30) == 30",
        "assert clamp_score(-5) == 0\nassert clamp_score(150) == 100",
    ),
    ScenarioFamily(
        "boolean_parsing",
        "parse_bool",
        "Accept case-insensitive padded boolean text while preserving invalid-value rejection.",
        "def parse_bool(value):\n    if not isinstance(value, str):\n        raise TypeError('text required')\n    if value == 'true':\n        return True\n    if value == 'false':\n        return False\n    raise ValueError(value)\n",
        "def parse_bool(value):\n    if not isinstance(value, str):\n        raise TypeError('text required')\n    normalized = value.strip().lower()\n    if normalized == 'true':\n        return True\n    if normalized == 'false':\n        return False\n    raise ValueError(value)\n",
        "def parse_bool(value, allow_numeric=False):\n    if not isinstance(value, str):\n        if allow_numeric and value in (0, 1):\n            return bool(value)\n        raise TypeError('text required')\n    if value == 'true':\n        return True\n    if value == 'false':\n        return False\n    raise ValueError(value)\n",
        "def parse_bool(value, allow_numeric=False):\n    if allow_numeric and value in (0, 1):\n        return bool(value)\n    if not isinstance(value, str):\n        raise TypeError('text required')\n    normalized = value.strip().casefold()\n    if normalized not in ('false', 'true'):\n        raise ValueError(value)\n    return normalized > 'false'\n",
        "def parse_bool(value):\n    return bool(value)\n",
        "assert parse_bool(' TRUE ') is True\nassert parse_bool(' false ') is False\ntry:\n    parse_bool('perhaps')\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('invalid value accepted')",
        "assert parse_bool('true') is True\nassert parse_bool('false') is False\ntry:\n    parse_bool('perhaps')\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('invalid value accepted')",
    ),
    ScenarioFamily(
        "item_chunking",
        "chunks",
        "Optionally drop a short final chunk while preserving positive-size validation.",
        "def chunks(items, size):\n    if size <= 0:\n        raise ValueError('positive size required')\n    return [items[index:index + size] for index in range(0, len(items), size)]\n",
        "def chunks(items, size, drop_partial=False):\n    if size <= 0:\n        raise ValueError('positive size required')\n    output = [items[index:index + size] for index in range(0, len(items), size)]\n    if drop_partial and output and len(output[-1]) < size:\n        output.pop()\n    return output\n",
        "def chunks(items, size, start=0):\n    if size <= 0:\n        raise ValueError('positive size required')\n    return [items[index:index + size] for index in range(start, len(items), size)]\n",
        "def chunks(items, size, drop_partial=False):\n    if size < 1:\n        raise ValueError('positive size required')\n    output = []\n    for index in range(0, len(items), size):\n        part = items[index:index + size]\n        if len(part) == size or not drop_partial:\n            output.append(part)\n    return output\n",
        "def chunks(items, size, drop_partial=False):\n    return [items]\n",
        "assert chunks([1, 2, 3], 2, drop_partial=True) == [[1, 2]]\nassert chunks([1, 2, 3], 2) == [[1, 2], [3]]",
        "assert chunks([1, 2, 3], 2) == [[1, 2], [3]]\ntry:\n    chunks([1], 0)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('size validation lost')",
    ),
    ScenarioFamily(
        "retry_backoff",
        "backoff",
        "Use exponential retry backoff while preserving non-negative delay validation.",
        "def backoff(delay, attempt):\n    if delay < 0 or attempt < 0:\n        raise ValueError('non-negative values required')\n    return delay * (attempt + 1)\n",
        "def backoff(delay, attempt):\n    if delay < 0 or attempt < 0:\n        raise ValueError('non-negative values required')\n    return delay * (2 ** attempt)\n",
        "def backoff(delay, attempt, max_delay=None):\n    if delay < 0 or attempt < 0:\n        raise ValueError('non-negative values required')\n    result = delay * (attempt + 1)\n    return min(result, max_delay) if max_delay is not None else result\n",
        "def backoff(delay, attempt, max_delay=None):\n    if not delay >= 0 <= attempt:\n        raise ValueError('non-negative values required')\n    result = delay * (1 << attempt)\n    return min(result, max_delay) if max_delay is not None else result\n",
        "def backoff(delay, attempt):\n    return delay * (2 ** attempt)\n",
        "assert backoff(3, 0) == 3\nassert backoff(3, 3) == 24",
        "assert backoff(3, 0) == 3\ntry:\n    backoff(-1, 2)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('delay validation lost')",
    ),
    ScenarioFamily(
        "path_joining",
        "join_path",
        "Ignore empty path segments while preserving slash normalization.",
        "def join_path(*parts):\n    return '/'.join(part.strip('/') for part in parts)\n",
        "def join_path(*parts):\n    cleaned = [part.strip('/') for part in parts if part.strip('/')]\n    return '/'.join(cleaned)\n",
        "def join_path(*parts, trailing=False):\n    result = '/'.join(part.strip('/') for part in parts)\n    return result + '/' if trailing else result\n",
        "def join_path(*parts):\n    output = []\n    for part in parts:\n        value = part.strip('/')\n        if value:\n            output.append(value)\n    return '/'.join(output)\n",
        "def join_path(*parts):\n    return '/'.join(reversed(parts))\n",
        "assert join_path('/a/', '', '/b/') == 'a/b'",
        "assert join_path('/a/', '/b/') == 'a/b'",
    ),
    ScenarioFamily(
        "configuration_merge",
        "merge_config",
        "Ignore None overrides while preserving defaults and input immutability.",
        "def merge_config(defaults, overrides):\n    return {**defaults, **overrides}\n",
        "def merge_config(defaults, overrides):\n    result = dict(defaults)\n    result.update({key: value for key, value in overrides.items() if value is not None})\n    return result\n",
        "def merge_config(defaults, overrides, strict=False):\n    if strict and any(key not in defaults for key in overrides):\n        raise KeyError('unknown setting')\n    return {**defaults, **overrides}\n",
        "def merge_config(defaults, overrides):\n    result = defaults.copy()\n    for key, value in overrides.items():\n        if value is not None:\n            result[key] = value\n    return result\n",
        "def merge_config(defaults, overrides):\n    defaults.update(overrides)\n    return defaults\n",
        "defaults = {'a': 1, 'b': 2}\nassert merge_config(defaults, {'a': None, 'b': 3}) == {'a': 1, 'b': 3}\nassert defaults == {'a': 1, 'b': 2}",
        "defaults = {'a': 1}\nassert merge_config(defaults, {'b': 2}) == {'a': 1, 'b': 2}\nassert defaults == {'a': 1}",
    ),
    ScenarioFamily(
        "status_routing",
        "select_route",
        "Return a retry route for unknown statuses while preserving known status mappings.",
        "def select_route(status):\n    routes = {200: 'ok', 404: 'missing'}\n    if status not in routes:\n        raise ValueError(status)\n    return routes[status]\n",
        "def select_route(status):\n    return {200: 'ok', 404: 'missing'}.get(status, 'retry')\n",
        "def select_route(status):\n    routes = {200: 'ok', 404: 'missing', 500: 'retry'}\n    if status not in routes:\n        raise ValueError(status)\n    return routes[status]\n",
        "def select_route(status):\n    routes = {200: 'ok', 404: 'missing'}\n    return routes[status] if status in routes else 'retry'\n",
        "def select_route(status):\n    return {200: 'retry', 404: 'missing'}.get(status, 'ok')\n",
        "assert select_route(200) == 'ok'\nassert select_route(418) == 'retry'",
        "assert select_route(200) == 'ok'\nassert select_route(404) == 'missing'",
    ),
    ScenarioFamily(
        "header_parsing",
        "parse_header",
        "Trim header names and values while preserving single-colon parsing.",
        "def parse_header(line):\n    if ':' not in line:\n        raise ValueError('missing colon')\n    return tuple(line.split(':', 1))\n",
        "def parse_header(line):\n    if ':' not in line:\n        raise ValueError('missing colon')\n    name, value = line.split(':', 1)\n    name, value = name.strip(), value.strip()\n    if not name:\n        raise ValueError('empty name')\n    return name, value\n",
        "def parse_header(line, max_parts=2):\n    if ':' not in line:\n        raise ValueError('missing colon')\n    return tuple(line.split(':', max_parts - 1))\n",
        "def parse_header(line):\n    if ':' not in line:\n        raise ValueError('missing colon')\n    pieces = line.split(':', 1)\n    result = tuple(piece.strip() for piece in pieces)\n    if not result[0]:\n        raise ValueError('empty name')\n    return result\n",
        "def parse_header(line):\n    if ':' not in line:\n        return '', line\n    name, value = line.split(':', 1)\n    return value, name\n",
        "assert parse_header(' Name : value:part ') == ('Name', 'value:part')\ntry:\n    parse_header(' : value')\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('empty name accepted')",
        "assert parse_header('Name:value:part') == ('Name', 'value:part')\ntry:\n    parse_header('missing')\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('missing colon accepted')",
    ),
    ScenarioFamily(
        "weighted_total",
        "total_weight",
        "Add optional overhead to item weights while preserving negative-weight rejection.",
        "def total_weight(items):\n    if any(weight < 0 for name, weight in items):\n        raise ValueError('negative weight')\n    return sum(weight for name, weight in items)\n",
        "def total_weight(items, overhead=0):\n    if any(weight < 0 for name, weight in items) or overhead < 0:\n        raise ValueError('negative weight')\n    return sum(weight for name, weight in items) + overhead\n",
        "def total_weight(items, rounded=False):\n    if any(weight < 0 for name, weight in items):\n        raise ValueError('negative weight')\n    result = sum(weight for name, weight in items)\n    return round(result) if rounded else result\n",
        "def total_weight(items, overhead=0, tax=0):\n    values = [overhead, tax] + [weight for name, weight in items]\n    if min(values) < 0:\n        raise ValueError('negative weight')\n    return sum(values[1:], values[0])\n",
        "def total_weight(items, overhead=0):\n    return sum(weight for name, weight in items) + overhead\n",
        "assert total_weight([('a', 2), ('b', 3)], overhead=4) == 9\ntry:\n    total_weight([('a', -1)])\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('negative weight accepted')",
        "assert total_weight([('a', 2), ('b', 3)]) == 5\ntry:\n    total_weight([('a', -1)])\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('negative weight accepted')",
    ),
    ScenarioFamily(
        "deadline_budget",
        "remaining_time",
        "Support an optional remaining-time cap while preserving zero-floor behavior.",
        "def remaining_time(deadline, now):\n    return max(0, deadline - now)\n",
        "def remaining_time(deadline, now, cap=None):\n    remaining = max(0, deadline - now)\n    return min(remaining, cap) if cap is not None else remaining\n",
        "def remaining_time(deadline, now, floor=0):\n    return max(floor, deadline - now)\n",
        "def remaining_time(deadline, now, cap=None, floor=0):\n    result = max(floor, deadline - now)\n    return -max(-result, -cap) if cap is not None else result\n",
        "def remaining_time(deadline, now, cap=None):\n    return deadline - now\n",
        "assert remaining_time(20, 5, cap=7) == 7\nassert remaining_time(5, 20, cap=7) == 0",
        "assert remaining_time(20, 5) == 15\nassert remaining_time(5, 20) == 0",
    ),
    ScenarioFamily(
        "secret_redaction",
        "redact",
        "Allow a custom redaction marker while preserving complete secret replacement.",
        "def redact(text, secret):\n    if not secret:\n        raise ValueError('secret required')\n    return text.replace(secret, '***')\n",
        "def redact(text, secret, marker='***'):\n    if not secret:\n        raise ValueError('secret required')\n    return text.replace(secret, marker)\n",
        "def redact(text, secret, count=-1):\n    if not secret:\n        raise ValueError('secret required')\n    return text.replace(secret, '***', count)\n",
        "def redact(text, secret, marker='***'):\n    if secret == '':\n        raise ValueError('secret required')\n    return marker.join(text.split(secret))\n",
        "def redact(text, secret, marker='***'):\n    return text\n",
        "assert redact('x token token', 'token', marker='[redacted]') == 'x [redacted] [redacted]'",
        "assert redact('x token token', 'token') == 'x *** ***'\ntry:\n    redact('x', '')\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('empty secret accepted')",
    ),
    ScenarioFamily(
        "state_transition",
        "transition",
        "Make state transitions idempotent while preserving transition validation.",
        "def transition(current, requested):\n    allowed = {('new', 'ready'), ('ready', 'done')}\n    if (current, requested) not in allowed:\n        raise ValueError('invalid transition')\n    return requested\n",
        "def transition(current, requested):\n    if current == requested:\n        return current\n    allowed = {('new', 'ready'), ('ready', 'done')}\n    if (current, requested) not in allowed:\n        raise ValueError('invalid transition')\n    return requested\n",
        "def transition(current, requested):\n    allowed = {('new', 'ready'), ('ready', 'done'), ('done', 'new')}\n    if (current, requested) not in allowed:\n        raise ValueError('invalid transition')\n    return requested\n",
        "def transition(current, requested):\n    allowed = {'new': {'ready'}, 'ready': {'done'}}\n    if current == requested:\n        return current\n    if requested not in allowed.get(current, set()):\n        raise ValueError('invalid transition')\n    return requested\n",
        "def transition(current, requested):\n    return requested\n",
        "assert transition('ready', 'ready') == 'ready'\nassert transition('new', 'ready') == 'ready'",
        "assert transition('new', 'ready') == 'ready'\ntry:\n    transition('new', 'done')\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('invalid transition accepted')",
    ),
    ScenarioFamily(
        "slot_selection",
        "acquire_slot",
        "Honor a preferred free slot while preserving the first-free fallback.",
        "def acquire_slot(occupied):\n    for index, used in enumerate(occupied):\n        if not used:\n            return index\n    return -1\n",
        "def acquire_slot(occupied, preferred=None):\n    if preferred is not None and 0 <= preferred < len(occupied) and not occupied[preferred]:\n        return preferred\n    for index, used in enumerate(occupied):\n        if not used:\n            return index\n    return -1\n",
        "def acquire_slot(occupied, reverse=False):\n    indexes = range(len(occupied) - 1, -1, -1) if reverse else range(len(occupied))\n    for index in indexes:\n        if not occupied[index]:\n            return index\n    return -1\n",
        "def acquire_slot(occupied, preferred=None):\n    candidates = [index for index, used in enumerate(occupied) if not used]\n    if preferred in candidates:\n        return preferred\n    return candidates[0] if candidates else -1\n",
        "def acquire_slot(occupied, preferred=None):\n    return 0 if occupied else -1\n",
        "assert acquire_slot([False, False, True], preferred=1) == 1\nassert acquire_slot([True, False], preferred=0) == 1",
        "assert acquire_slot([True, False, True]) == 1\nassert acquire_slot([True, True]) == -1",
    ),
    ScenarioFamily(
        "checksum_verification",
        "verify_checksum",
        "Accept hexadecimal checksum text while preserving mismatch detection.",
        "def verify_checksum(data, expected):\n    return sum(data) % 256 == expected\n",
        "def verify_checksum(data, expected):\n    if isinstance(expected, str):\n        expected = int(expected, 16)\n    return sum(data) % 256 == expected\n",
        "def verify_checksum(data, expected, strict_bytes=False):\n    if strict_bytes and not isinstance(data, bytes):\n        raise TypeError('bytes required')\n    return sum(data) % 256 == expected\n",
        "def verify_checksum(data, expected):\n    numeric = int(expected, 16) if isinstance(expected, str) else expected\n    return (sum(data) & 255) == numeric\n",
        "def verify_checksum(data, expected):\n    return True\n",
        "assert verify_checksum(bytes([1, 2, 3]), '06') is True\nassert verify_checksum(bytes([1, 2, 3]), '07') is False",
        "assert verify_checksum(bytes([1, 2, 3]), 6) is True\nassert verify_checksum(bytes([1, 2, 3]), 7) is False",
    ),
    ScenarioFamily(
        "version_comparison",
        "newer",
        "Accept a leading v in versions while preserving numeric component comparison.",
        "def newer(left, right):\n    return tuple(int(part) for part in left.split('.')) > tuple(int(part) for part in right.split('.'))\n",
        "def newer(left, right):\n    left = left.removeprefix('v')\n    right = right.removeprefix('v')\n    return tuple(int(part) for part in left.split('.')) > tuple(int(part) for part in right.split('.'))\n",
        "def newer(left, right, components=None):\n    a = tuple(int(part) for part in left.split('.'))\n    b = tuple(int(part) for part in right.split('.'))\n    return a[:components] > b[:components] if components else a > b\n",
        "def newer(left, right, components=None):\n    left_parts = [int(part) for part in left.removeprefix('v').split('.')]\n    right_parts = [int(part) for part in right.removeprefix('v').split('.')]\n    if components is not None:\n        left_parts, right_parts = left_parts[:components], right_parts[:components]\n    for left_part, right_part in zip(left_parts, right_parts):\n        if left_part != right_part:\n            return left_part - right_part > 0\n    return len(left_parts) > len(right_parts)\n",
        "def newer(left, right):\n    return left > right\n",
        "assert newer('v10.0', 'v2.0') is True\nassert newer('v1.0', 'v2.0') is False",
        "assert newer('10.0', '2.0') is True\nassert newer('1.0', '2.0') is False",
    ),
    ScenarioFamily(
        "structured_logging",
        "log_record",
        "Attach an optional request identifier while preserving the message field.",
        "def log_record(message):\n    return {'message': str(message)}\n",
        "def log_record(message, request_id=None):\n    record = {'message': str(message)}\n    if request_id is not None:\n        record['request_id'] = request_id\n    return record\n",
        "def log_record(message, timestamp=None):\n    record = {'message': str(message)}\n    if timestamp is not None:\n        record['timestamp'] = timestamp\n    return record\n",
        "def log_record(message, request_id=None):\n    fields = [('message', str(message))]\n    if request_id is not None:\n        fields.append(('request_id', request_id))\n    return dict(fields)\n",
        "def log_record(message, request_id=None):\n    return {'request_id': request_id}\n",
        "assert log_record('ready', request_id='r1') == {'message': 'ready', 'request_id': 'r1'}\nassert log_record('ready') == {'message': 'ready'}",
        "assert log_record('ready') == {'message': 'ready'}",
    ),
    ScenarioFamily(
        "job_scheduling",
        "schedule",
        "Support descending priority order while preserving stable ascending scheduling.",
        "def schedule(jobs):\n    return sorted(jobs, key=lambda job: job[0])\n",
        "def schedule(jobs, descending=False):\n    return sorted(jobs, key=lambda job: job[0], reverse=descending)\n",
        "def schedule(jobs, limit=None):\n    ordered = sorted(jobs, key=lambda job: job[0])\n    return ordered[:limit] if limit is not None else ordered\n",
        "def schedule(jobs, descending=False):\n    direction = -1 if descending else 1\n    return sorted(jobs, key=lambda job: direction * job[0])\n",
        "def schedule(jobs, descending=False):\n    return sorted(jobs, key=lambda job: job[0], reverse=True)\n",
        "jobs = [(2, 'b'), (1, 'a'), (2, 'c')]\nassert schedule(jobs, descending=True) == [(2, 'b'), (2, 'c'), (1, 'a')]",
        "jobs = [(2, 'b'), (1, 'a'), (2, 'c')]\nassert schedule(jobs) == [(1, 'a'), (2, 'b'), (2, 'c')]",
    ),
    ScenarioFamily(
        "token_consumption",
        "consume",
        "Enforce a minimum remaining balance while preserving amount validation.",
        "def consume(tokens, amount):\n    if amount < 0:\n        raise ValueError('negative amount')\n    if amount > tokens:\n        raise ValueError('insufficient tokens')\n    return tokens - amount\n",
        "def consume(tokens, amount, minimum_remaining=0):\n    if amount < 0:\n        raise ValueError('negative amount')\n    remaining = tokens - amount\n    if remaining < minimum_remaining:\n        raise ValueError('insufficient tokens')\n    return remaining\n",
        "def consume(tokens, amount, fee=0):\n    if amount < 0 or fee < 0:\n        raise ValueError('negative amount')\n    if amount + fee > tokens:\n        raise ValueError('insufficient tokens')\n    return tokens - amount - fee\n",
        "def consume(tokens, amount, minimum_remaining=0):\n    if amount < 0:\n        raise ValueError('negative amount')\n    result = tokens - amount\n    if min(result, minimum_remaining) != minimum_remaining:\n        raise ValueError('insufficient tokens')\n    return result\n",
        "def consume(tokens, amount, minimum_remaining=0):\n    return tokens - amount\n",
        "assert consume(10, 4, minimum_remaining=5) == 6\ntry:\n    consume(10, 6, minimum_remaining=5)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('minimum balance ignored')",
        "assert consume(10, 4) == 6\ntry:\n    consume(10, -1)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('negative amount accepted')",
    ),
    ScenarioFamily(
        "range_validation",
        "in_range",
        "Support exclusive bounds while preserving invalid-bound rejection.",
        "def in_range(value, low, high):\n    if low > high:\n        raise ValueError('invalid bounds')\n    return low <= value <= high\n",
        "def in_range(value, low, high, inclusive=True):\n    if low > high:\n        raise ValueError('invalid bounds')\n    return low <= value <= high if inclusive else low < value < high\n",
        "def in_range(value, low, high, clamp=False):\n    if low > high:\n        raise ValueError('invalid bounds')\n    if clamp:\n        value = max(low, min(high, value))\n    return low <= value <= high\n",
        "def in_range(value, low, high, inclusive=True, normalize=False):\n    if normalize and low > high:\n        low, high = high, low\n    width = high - low\n    if width < 0:\n        raise ValueError('invalid bounds')\n    distance = abs(2 * value - low - high)\n    return distance <= width if inclusive else distance < width\n",
        "def in_range(value, low, high, inclusive=True):\n    low, high = min(low, high), max(low, high)\n    return low <= value <= high\n",
        "assert in_range(1, 1, 3, inclusive=False) is False\nassert in_range(2, 1, 3, inclusive=False) is True",
        "assert in_range(1, 1, 3) is True\ntry:\n    in_range(2, 3, 1)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('invalid bounds accepted')",
    ),
    ScenarioFamily(
        "memoization_key",
        "memo_key",
        "Include sorted keyword arguments while preserving positional key identity.",
        "def memo_key(*args):\n    return tuple(args)\n",
        "def memo_key(*args, **kwargs):\n    return tuple(args) + tuple(sorted(kwargs.items()))\n",
        "def memo_key(*args, **kwargs):\n    return tuple(args) + tuple(kwargs.items())\n",
        "def memo_key(*args, **kwargs):\n    items = list(kwargs.items())\n    items.sort()\n    return tuple(args) + tuple(items)\n",
        "def memo_key(*args, **kwargs):\n    return tuple(sorted(kwargs.items()))\n",
        "assert memo_key(1, b=2, a=3) == (1, ('a', 3), ('b', 2))",
        "assert memo_key(1, 2) == (1, 2)",
    ),
    ScenarioFamily(
        "query_encoding",
        "encode_query",
        "Sort query keys and omit None values while preserving key-value encoding.",
        "def encode_query(params):\n    return '&'.join(str(key) + '=' + str(value) for key, value in params.items())\n",
        "def encode_query(params):\n    return '&'.join(str(key) + '=' + str(params[key]) for key in sorted(params) if params[key] is not None)\n",
        "def encode_query(params):\n    return '&'.join(str(key) + '=' + str(params[key]) for key in sorted(params))\n",
        "def encode_query(params):\n    pairs = []\n    for key in sorted(params):\n        if params[key] is not None:\n            pairs.append(str(key) + '=' + str(params[key]))\n    return '&'.join(pairs)\n",
        "def encode_query(params):\n    return '&'.join(str(value) for value in params.values())\n",
        "assert encode_query({'b': 2, 'a': 1, 'skip': None}) == 'a=1&b=2'",
        "assert encode_query({'a': 1}) == 'a=1'",
    ),
    ScenarioFamily(
        "dependency_readiness",
        "ready_nodes",
        "Return ready dependency nodes deterministically while excluding blocked nodes.",
        "def ready_nodes(graph, completed):\n    return [node for node, deps in graph.items() if all(dep in completed for dep in deps)]\n",
        "def ready_nodes(graph, completed):\n    ready = [node for node, deps in graph.items() if all(dep in completed for dep in deps)]\n    return sorted(ready)\n",
        "def ready_nodes(graph, completed):\n    return [node for node, deps in graph.items() if set(deps) <= set(completed)]\n",
        "def ready_nodes(graph, completed):\n    output = []\n    for node in sorted(graph):\n        if all(dependency in completed for dependency in graph[node]):\n            output.append(node)\n    return output\n",
        "def ready_nodes(graph, completed):\n    return list(graph)\n",
        "graph = {'b': [], 'a': [], 'c': ['missing']}\nassert ready_nodes(graph, set()) == ['a', 'b']",
        "graph = {'ready': [], 'blocked': ['missing']}\nassert ready_nodes(graph, set()) == ['ready']",
    ),
    ScenarioFamily(
        "name_filtering",
        "filter_names",
        "Add case-insensitive prefix filtering while preserving input order.",
        "def filter_names(names, prefix):\n    return [name for name in names if name.startswith(prefix)]\n",
        "def filter_names(names, prefix, case_sensitive=True):\n    if case_sensitive:\n        return [name for name in names if name.startswith(prefix)]\n    target = prefix.lower()\n    return [name for name in names if name.lower().startswith(target)]\n",
        "def filter_names(names, prefix, limit=None):\n    output = [name for name in names if name.startswith(prefix)]\n    return output[:limit] if limit is not None else output\n",
        "def filter_names(names, prefix, case_sensitive=True):\n    match = (lambda name: name.startswith(prefix)) if case_sensitive else (lambda name: name.casefold().startswith(prefix.casefold()))\n    return [name for name in names if match(name)]\n",
        "def filter_names(names, prefix, case_sensitive=True):\n    return sorted(name for name in names if prefix in name)\n",
        "names = ['Alpha', 'beta', 'apple']\nassert filter_names(names, 'a', case_sensitive=False) == ['Alpha', 'apple']",
        "assert filter_names(['ab', 'ba', 'ac'], 'a') == ['ab', 'ac']",
    ),
    ScenarioFamily(
        "record_indexing",
        "index_records",
        "Optionally reject duplicate record identifiers while preserving last-write indexing.",
        "def index_records(records):\n    return {record['id']: record for record in records}\n",
        "def index_records(records, reject_duplicates=False):\n    output = {}\n    for record in records:\n        key = record['id']\n        if reject_duplicates and key in output:\n            raise ValueError('duplicate id')\n        output[key] = record\n    return output\n",
        "def index_records(records, copy_records=False):\n    return {record['id']: dict(record) if copy_records else record for record in records}\n",
        "def index_records(records, reject_duplicates=False):\n    output = {}\n    for item in records:\n        if reject_duplicates and item['id'] in output:\n            raise ValueError('duplicate id')\n        output[item['id']] = item\n    return output\n",
        "def index_records(records, reject_duplicates=False):\n    return {index: record for index, record in enumerate(records)}\n",
        "records = [{'id': 1, 'v': 'a'}, {'id': 1, 'v': 'b'}]\ntry:\n    index_records(records, reject_duplicates=True)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('duplicate accepted')\nassert index_records(records)[1]['v'] == 'b'",
        "records = [{'id': 1}, {'id': 2}]\nresult = index_records(records)\nassert set(result) == {1, 2}",
    ),
    ScenarioFamily(
        "metric_averaging",
        "average",
        "Allow a default for empty metrics while preserving arithmetic means.",
        "def average(values):\n    if not values:\n        raise ValueError('values required')\n    return sum(values) / len(values)\n",
        "def average(values, default=None):\n    if not values:\n        if default is None:\n            raise ValueError('values required')\n        return default\n    return sum(values) / len(values)\n",
        "def average(values, digits=None):\n    if not values:\n        raise ValueError('values required')\n    result = sum(values) / len(values)\n    return round(result, digits) if digits is not None else result\n",
        "def average(values, default=None):\n    if len(values) == 0:\n        if default is None:\n            raise ValueError('values required')\n        return default\n    return sum(values) / len(values)\n",
        "def average(values, default=None):\n    return default if not values else sum(values)\n",
        "assert average([], default=0) == 0\nassert average([2, 4], default=0) == 3",
        "assert average([2, 4]) == 3\ntry:\n    average([])\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('empty input accepted')",
    ),
    ScenarioFamily(
        "event_coalescing",
        "coalesce",
        "Coalesce only adjacent duplicate events while preserving event order.",
        "def coalesce(events):\n    return list(dict.fromkeys(events))\n",
        "def coalesce(events):\n    output = []\n    for event in events:\n        if not output or output[-1] != event:\n            output.append(event)\n    return output\n",
        "def coalesce(events, reverse=False):\n    values = list(dict.fromkeys(events))\n    return list(reversed(values)) if reverse else values\n",
        "def coalesce(events):\n    if not events:\n        return []\n    output = [events[0]]\n    for event in events[1:]:\n        if event != output[-1]:\n            output.append(event)\n    return output\n",
        "def coalesce(events):\n    return sorted(set(events))\n",
        "assert coalesce(['a', 'a', 'b', 'a']) == ['a', 'b', 'a']",
        "assert coalesce(['b', 'a']) == ['b', 'a']",
    ),
    ScenarioFamily(
        "interval_overlap",
        "overlaps",
        "Support exclusive interval endpoints while preserving ordered-bound validation.",
        "def overlaps(left, right):\n    if left[0] > left[1] or right[0] > right[1]:\n        raise ValueError('invalid interval')\n    return max(left[0], right[0]) <= min(left[1], right[1])\n",
        "def overlaps(left, right, inclusive=True):\n    if left[0] > left[1] or right[0] > right[1]:\n        raise ValueError('invalid interval')\n    start = max(left[0], right[0])\n    end = min(left[1], right[1])\n    return start <= end if inclusive else start < end\n",
        "def overlaps(left, right, tolerance=0):\n    if left[0] > left[1] or right[0] > right[1]:\n        raise ValueError('invalid interval')\n    return max(left[0], right[0]) <= min(left[1], right[1]) + tolerance\n",
        "def overlaps(left, right, inclusive=True, tolerance=0):\n    invalidity = max(left[0] - left[1], right[0] - right[1])\n    if invalidity > 0:\n        raise ValueError('invalid interval')\n    separation = max(left[0], right[0]) - min(left[1], right[1])\n    return separation <= tolerance if inclusive else separation < tolerance\n",
        "def overlaps(left, right, inclusive=True):\n    return True\n",
        "assert overlaps((0, 1), (1, 2), inclusive=False) is False\nassert overlaps((0, 2), (1, 3), inclusive=False) is True",
        "assert overlaps((0, 1), (1, 2)) is True\ntry:\n    overlaps((2, 1), (0, 1))\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('invalid interval accepted')",
    ),
    ScenarioFamily(
        "quota_allocation",
        "allocate",
        "Reserve capacity during allocation while preserving quota exhaustion checks.",
        "def allocate(capacity, requested):\n    if requested < 0 or requested > capacity:\n        raise ValueError('invalid request')\n    return capacity - requested\n",
        "def allocate(capacity, requested, reserve=0):\n    if requested < 0 or reserve < 0 or capacity - requested < reserve:\n        raise ValueError('invalid request')\n    return capacity - requested\n",
        "def allocate(capacity, requested, bonus=0):\n    if requested < 0 or requested > capacity + bonus:\n        raise ValueError('invalid request')\n    return capacity + bonus - requested\n",
        "def allocate(capacity, requested, reserve=0):\n    remaining = capacity - requested\n    if min(requested, reserve) < 0 or remaining < reserve:\n        raise ValueError('invalid request')\n    return remaining\n",
        "def allocate(capacity, requested, reserve=0):\n    return max(0, capacity - requested)\n",
        "assert allocate(10, 4, reserve=5) == 6\ntry:\n    allocate(10, 6, reserve=5)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('reserve ignored')",
        "assert allocate(10, 4) == 6\ntry:\n    allocate(3, 4)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('capacity exhaustion ignored')",
    ),
    ScenarioFamily(
        "alias_resolution",
        "resolve_alias",
        "Resolve chained aliases while preserving cycle rejection.",
        "def resolve_alias(name, aliases):\n    target = aliases.get(name, name)\n    if aliases.get(target) == name:\n        raise ValueError('cycle')\n    return target\n",
        "def resolve_alias(name, aliases):\n    seen = set()\n    while name in aliases:\n        if name in seen:\n            raise ValueError('cycle')\n        seen.add(name)\n        name = aliases[name]\n    return name\n",
        "def resolve_alias(name, aliases, default=None):\n    target = aliases.get(name, default if default is not None else name)\n    if aliases.get(target) == name:\n        raise ValueError('cycle')\n    return target\n",
        "def resolve_alias(name, aliases):\n    visited = []\n    while name in aliases:\n        if name in visited:\n            raise ValueError('cycle')\n        visited.append(name)\n        name = aliases[name]\n    return name\n",
        "def resolve_alias(name, aliases):\n    return aliases.get(name, name)\n",
        "assert resolve_alias('a', {'a': 'b', 'b': 'c'}) == 'c'\ntry:\n    resolve_alias('a', {'a': 'b', 'b': 'a'})\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('cycle accepted')",
        "assert resolve_alias('a', {'a': 'b'}) == 'b'\ntry:\n    resolve_alias('a', {'a': 'b', 'b': 'a'})\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('cycle accepted')",
    ),
    ScenarioFamily(
        "threshold_classification",
        "classify",
        "Support an explicit boundary label while preserving low/high classification.",
        "def classify(value, threshold):\n    return 'high' if value >= threshold else 'low'\n",
        "def classify(value, threshold, boundary='high'):\n    if value == threshold:\n        return boundary\n    return 'high' if value > threshold else 'low'\n",
        "def classify(value, threshold, labels=('low', 'high')):\n    return labels[1] if value >= threshold else labels[0]\n",
        "def classify(value, threshold, boundary='high'):\n    if value < threshold:\n        return 'low'\n    if value > threshold:\n        return 'high'\n    return boundary\n",
        "def classify(value, threshold, boundary='high'):\n    return 'low' if value >= threshold else 'high'\n",
        "assert classify(5, 5, boundary='edge') == 'edge'\nassert classify(6, 5, boundary='edge') == 'high'",
        "assert classify(6, 5) == 'high'\nassert classify(4, 5) == 'low'",
    ),
)


FRESH_SCENARIO_FAMILIES = (
    ScenarioFamily(
        "whitespace_runs",
        "clean_text",
        "Optionally collapse internal whitespace while preserving ordinary edge trimming.",
        "def clean_text(value):\n    return value.strip()\n",
        "def clean_text(value, collapse=False):\n    value = value.strip()\n    return ' '.join(value.split()) if collapse else value\n",
        "def clean_text(value, lowercase=False):\n    value = value.strip()\n    return value.lower() if lowercase else value\n",
        "def clean_text(value, collapse=False):\n    original = value.strip()\n    choices = (original, ' '.join(original.split()))\n    return choices[int(bool(collapse))]\n",
        "def clean_text(value, collapse=False):\n    return ' '.join(str(value).split())\n",
        "assert clean_text('  a   b  ', collapse=True) == 'a b'\nassert clean_text('  a   b  ') == 'a   b'",
        "assert clean_text('  a   b  ') == 'a   b'",
    ),
    ScenarioFamily(
        "suffix_replacement",
        "ensure_suffix",
        "Optionally replace an existing final suffix while preserving append-only behavior by default.",
        "def ensure_suffix(value, suffix):\n    return value if value.endswith(suffix) else value + suffix\n",
        "def ensure_suffix(value, suffix, replace_existing=False):\n    if replace_existing and '.' in value.rsplit('/', 1)[-1]:\n        value = value.rsplit('.', 1)[0]\n    return value if value.endswith(suffix) else value + suffix\n",
        "def ensure_suffix(value, suffix, case_sensitive=True):\n    present = value.endswith(suffix) if case_sensitive else value.lower().endswith(suffix.lower())\n    return value if present else value + suffix\n",
        "def ensure_suffix(value, suffix, replace_existing=False):\n    tail = value.rsplit('/', 1)[-1]\n    cut = len(value) - len(tail) + tail.rfind('.')\n    candidates = (value, value[:cut])\n    selected = candidates[int(bool(replace_existing and '.' in tail))]\n    return selected + ('' if selected.endswith(suffix) else suffix)\n",
        "def ensure_suffix(value, suffix, replace_existing=False):\n    return value + suffix\n",
        "assert ensure_suffix('report.txt', '.json', replace_existing=True) == 'report.json'\nassert ensure_suffix('dir.v1/report', '.json', replace_existing=True) == 'dir.v1/report.json'",
        "assert ensure_suffix('report.txt', '.txt') == 'report.txt'\nassert ensure_suffix('report', '.txt') == 'report.txt'",
    ),
    ScenarioFamily(
        "nullable_overlay",
        "overlay",
        "Allow None-valued updates to be ignored while preserving non-mutating overlay semantics.",
        "def overlay(defaults, updates):\n    return {**defaults, **updates}\n",
        "def overlay(defaults, updates, ignore_none=False):\n    result = dict(defaults)\n    result.update({key: value for key, value in updates.items() if not ignore_none or value is not None})\n    return result\n",
        "def overlay(defaults, updates, strict=False):\n    if strict and any(key not in defaults for key in updates):\n        raise KeyError('unknown key')\n    return {**defaults, **updates}\n",
        "def overlay(defaults, updates, ignore_none=False):\n    result = defaults.copy()\n    keep = lambda value: int(not ignore_none or value is not None)\n    pairs = [(key, value) for key, value in updates.items() if keep(value)]\n    result.update(dict(pairs))\n    return result\n",
        "def overlay(defaults, updates, ignore_none=False):\n    defaults.update(updates)\n    return defaults\n",
        "base = {'a': 1, 'b': 2}\nassert overlay(base, {'a': None, 'b': 3}, ignore_none=True) == {'a': 1, 'b': 3}\nassert base == {'a': 1, 'b': 2}",
        "base = {'a': 1}\nassert overlay(base, {'b': 2}) == {'a': 1, 'b': 2}\nassert base == {'a': 1}",
    ),
    ScenarioFamily(
        "capped_advance",
        "advance",
        "Support an optional maximum while preserving ordinary positive and negative steps.",
        "def advance(value, step=1):\n    return value + step\n",
        "def advance(value, step=1, maximum=None):\n    result = value + step\n    return min(result, maximum) if maximum is not None else result\n",
        "def advance(value, step=1, minimum=None):\n    result = value + step\n    return max(result, minimum) if minimum is not None else result\n",
        "def advance(value, step=1, maximum=None):\n    result = value + step\n    candidates = (result, maximum)\n    limit = candidates[int(maximum is not None)]\n    return min(result, limit)\n",
        "def advance(value, step=1, maximum=None):\n    return value - step\n",
        "assert advance(8, step=5, maximum=10) == 10\nassert advance(2, step=-4, maximum=10) == -2",
        "assert advance(2, step=3) == 5\nassert advance(2, step=-4) == -2",
    ),
    ScenarioFamily(
        "stable_ranking",
        "rank_items",
        "Support descending score order while preserving input order for tied scores.",
        "def rank_items(items):\n    return sorted(items, key=lambda item: item[0])\n",
        "def rank_items(items, descending=False):\n    return sorted(items, key=lambda item: item[0], reverse=descending)\n",
        "def rank_items(items, limit=None):\n    ordered = sorted(items, key=lambda item: item[0])\n    return ordered[:limit] if limit is not None else ordered\n",
        "def rank_items(items, descending=False):\n    decorated = [(score * (-1 if descending else 1), index, value) for index, (score, value) in enumerate(items)]\n    decorated.sort()\n    return [(items[index][0], value) for _, index, value in decorated]\n",
        "def rank_items(items, descending=False):\n    return list(reversed(sorted(items, key=lambda item: item[0])))\n",
        "items = [(2, 'first'), (1, 'low'), (2, 'second')]\nassert rank_items(items, descending=True) == [(2, 'first'), (2, 'second'), (1, 'low')]",
        "items = [(2, 'first'), (1, 'low'), (2, 'second')]\nassert rank_items(items) == [(1, 'low'), (2, 'first'), (2, 'second')]",
    ),
    ScenarioFamily(
        "casefold_lookup",
        "lookup",
        "Support case-insensitive key lookup while preserving exact lookup by default.",
        "def lookup(mapping, key):\n    return mapping[key]\n",
        "def lookup(mapping, key, case_sensitive=True):\n    if case_sensitive:\n        return mapping[key]\n    target = key.casefold()\n    for candidate, value in mapping.items():\n        if candidate.casefold() == target:\n            return value\n    raise KeyError(key)\n",
        "def lookup(mapping, key, aliases=None):\n    if aliases and key in aliases:\n        key = aliases[key]\n    return mapping[key]\n",
        "def lookup(mapping, key, case_sensitive=True):\n    keys = list(mapping)\n    probes = [candidate == key if case_sensitive else candidate.casefold() == key.casefold() for candidate in keys]\n    if True not in probes:\n        raise KeyError(key)\n    return mapping[keys[probes.index(True)]]\n",
        "def lookup(mapping, key, case_sensitive=True):\n    return next(iter(mapping.values()))\n",
        "assert lookup({'Name': 3}, 'name', case_sensitive=False) == 3\ntry:\n    lookup({'Name': 3}, 'missing', case_sensitive=False)\nexcept KeyError:\n    pass\nelse:\n    raise AssertionError('missing key accepted')",
        "assert lookup({'Name': 3}, 'Name') == 3\ntry:\n    lookup({'Name': 3}, 'name')\nexcept KeyError:\n    pass\nelse:\n    raise AssertionError('exact lookup weakened')",
    ),
    ScenarioFamily(
        "strided_windows",
        "windows",
        "Support a custom window stride while preserving complete-window filtering.",
        "def windows(values, size):\n    if size < 1:\n        raise ValueError('positive size required')\n    return [values[index:index + size] for index in range(len(values) - size + 1)]\n",
        "def windows(values, size, stride=1):\n    if size < 1 or stride < 1:\n        raise ValueError('positive size and stride required')\n    return [values[index:index + size] for index in range(0, len(values) - size + 1, stride)]\n",
        "def windows(values, size, partial=False):\n    if size < 1:\n        raise ValueError('positive size required')\n    stop = len(values) if partial else len(values) - size + 1\n    return [values[index:index + size] for index in range(stop)]\n",
        "def windows(values, size, stride=1):\n    invalid = min(size, stride) < 1\n    if invalid:\n        raise ValueError('positive size and stride required')\n    starts = list(range(len(values) - size + 1))\n    return [values[index:index + size] for index in starts if index % stride == 0]\n",
        "def windows(values, size, stride=1):\n    return [values[index:] for index in range(0, len(values), stride)]\n",
        "assert windows([0, 1, 2, 3, 4], 2, stride=2) == [[0, 1], [2, 3]]\ntry:\n    windows([1], 1, stride=0)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('stride validation lost')",
        "assert windows([0, 1, 2], 2) == [[0, 1], [1, 2]]\ntry:\n    windows([], 0)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('size validation lost')",
    ),
    ScenarioFamily(
        "scope_coverage",
        "has_scopes",
        "Optionally require every requested scope while preserving any-scope matching by default.",
        "def has_scopes(requested, granted):\n    return any(scope in granted for scope in requested)\n",
        "def has_scopes(requested, granted, require_all=False):\n    check = all if require_all else any\n    return check(scope in granted for scope in requested)\n",
        "def has_scopes(requested, granted, allow_empty=False):\n    if allow_empty and not requested:\n        return True\n    return any(scope in granted for scope in requested)\n",
        "def has_scopes(requested, granted, require_all=False):\n    matches = sum(scope in granted for scope in requested)\n    thresholds = (1, len(requested))\n    needed = thresholds[int(bool(require_all))]\n    return matches >= needed\n",
        "def has_scopes(requested, granted, require_all=False):\n    return set(requested) <= set(granted)\n",
        "assert has_scopes(['read', 'write'], {'read'}, require_all=True) is False\nassert has_scopes(['read', 'write'], {'read', 'write'}, require_all=True) is True",
        "assert has_scopes(['read', 'write'], {'read'}) is True\nassert has_scopes(['write'], {'read'}) is False",
    ),
    ScenarioFamily(
        "right_closed_buckets",
        "bucket",
        "Support right-closed threshold buckets while preserving left-closed indexing by default.",
        "def bucket(value, thresholds):\n    return sum(value >= threshold for threshold in thresholds)\n",
        "def bucket(value, thresholds, right_closed=False):\n    compare = (lambda threshold: value > threshold) if right_closed else (lambda threshold: value >= threshold)\n    return sum(compare(threshold) for threshold in thresholds)\n",
        "def bucket(value, thresholds, reverse=False):\n    result = sum(value >= threshold for threshold in thresholds)\n    return len(thresholds) - result if reverse else result\n",
        "def bucket(value, thresholds, right_closed=False):\n    offsets = [int(value == threshold and right_closed) for threshold in thresholds]\n    return sum(value >= threshold for threshold in thresholds) - sum(offsets)\n",
        "def bucket(value, thresholds, right_closed=False):\n    return sum(value > threshold for threshold in thresholds)\n",
        "assert bucket(10, [10, 20], right_closed=True) == 0\nassert bucket(11, [10, 20], right_closed=True) == 1",
        "assert bucket(10, [10, 20]) == 1\nassert bucket(20, [10, 20]) == 2",
    ),
    ScenarioFamily(
        "header_canonicalization",
        "canonical_headers",
        "Optionally lowercase header names while preserving values and non-mutating behavior.",
        "def canonical_headers(headers):\n    return dict(headers)\n",
        "def canonical_headers(headers, lower_names=False):\n    return {(name.lower() if lower_names else name): value for name, value in headers.items()}\n",
        "def canonical_headers(headers, strip_values=False):\n    return {name: value.strip() if strip_values else value for name, value in headers.items()}\n",
        "def canonical_headers(headers, lower_names=False):\n    result = {}\n    for pair in headers.items():\n        choices = (pair[0], pair[0].lower())\n        result[choices[int(bool(lower_names))]] = pair[1]\n    return result\n",
        "def canonical_headers(headers, lower_names=False):\n    return {name.lower(): str(value).lower() for name, value in headers.items()}\n",
        "source = {'Content-Type': 'Text/Plain'}\nassert canonical_headers(source, lower_names=True) == {'content-type': 'Text/Plain'}\nassert source == {'Content-Type': 'Text/Plain'}",
        "source = {'Content-Type': 'Text/Plain'}\nassert canonical_headers(source) == source\nassert source == {'Content-Type': 'Text/Plain'}",
    ),
    ScenarioFamily(
        "timeout_ceiling",
        "retry_timeout",
        "Support an optional retry-time ceiling while preserving linear retry scaling.",
        "def retry_timeout(base, attempt):\n    if base < 0 or attempt < 0:\n        raise ValueError('non-negative values required')\n    return base * (attempt + 1)\n",
        "def retry_timeout(base, attempt, ceiling=None):\n    if base < 0 or attempt < 0:\n        raise ValueError('non-negative values required')\n    value = base * (attempt + 1)\n    return min(value, ceiling) if ceiling is not None else value\n",
        "def retry_timeout(base, attempt, offset=0):\n    if base < 0 or attempt < 0 or offset < 0:\n        raise ValueError('non-negative values required')\n    return base * (attempt + 1) + offset\n",
        "def retry_timeout(base, attempt, ceiling=None):\n    if min(base, attempt) < 0:\n        raise ValueError('non-negative values required')\n    raw = base + base * attempt\n    candidates = (raw, min(raw, ceiling or raw))\n    return candidates[int(ceiling is not None)]\n",
        "def retry_timeout(base, attempt, ceiling=None):\n    return max(base * (attempt + 1), ceiling or 0)\n",
        "assert retry_timeout(3, 4, ceiling=10) == 10\nassert retry_timeout(3, 1, ceiling=10) == 6",
        "assert retry_timeout(3, 2) == 9\ntry:\n    retry_timeout(-1, 2)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('validation lost')",
    ),
    ScenarioFamily(
        "optional_weights",
        "weighted_average",
        "Accept optional weights while preserving the ordinary arithmetic mean by default.",
        "def weighted_average(values):\n    if not values:\n        raise ValueError('values required')\n    return sum(values) / len(values)\n",
        "def weighted_average(values, weights=None):\n    if not values:\n        raise ValueError('values required')\n    if weights is None:\n        return sum(values) / len(values)\n    if len(values) != len(weights) or sum(weights) == 0:\n        raise ValueError('invalid weights')\n    return sum(value * weight for value, weight in zip(values, weights)) / sum(weights)\n",
        "def weighted_average(values, digits=None):\n    if not values:\n        raise ValueError('values required')\n    result = sum(values) / len(values)\n    return round(result, digits) if digits is not None else result\n",
        "def weighted_average(values, weights=None):\n    if len(values) == 0:\n        raise ValueError('values required')\n    actual = weights if weights is not None else [1] * len(values)\n    denominator = sum(actual)\n    if len(values) != len(actual) or denominator == 0:\n        raise ValueError('invalid weights')\n    products = [pair[0] * pair[1] for pair in zip(values, actual)]\n    return sum(products) / denominator\n",
        "def weighted_average(values, weights=None):\n    return sum(values)\n",
        "assert weighted_average([2, 8], weights=[3, 1]) == 3.5\ntry:\n    weighted_average([1, 2], weights=[1])\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('weight mismatch accepted')",
        "assert weighted_average([2, 4]) == 3\ntry:\n    weighted_average([])\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('empty input accepted')",
    ),
    ScenarioFamily(
        "prefixed_selection",
        "select_keys",
        "Support optional key-prefix selection while preserving all keys by default.",
        "def select_keys(mapping):\n    return dict(mapping)\n",
        "def select_keys(mapping, prefix=None):\n    if prefix is None:\n        return dict(mapping)\n    return {key: value for key, value in mapping.items() if key.startswith(prefix)}\n",
        "def select_keys(mapping, limit=None):\n    pairs = list(mapping.items())\n    return dict(pairs[:limit] if limit is not None else pairs)\n",
        "def select_keys(mapping, prefix=None):\n    output = {}\n    marker = prefix is None\n    for key in mapping:\n        decisions = (key.startswith(prefix or ''), True)\n        if decisions[int(marker)]:\n            output[key] = mapping[key]\n    return output\n",
        "def select_keys(mapping, prefix=None):\n    return {key: mapping[key] for key in mapping if key.startswith('a')}\n",
        "source = {'db.host': 'x', 'api.host': 'y', 'db.port': 3}\nassert select_keys(source, prefix='db.') == {'db.host': 'x', 'db.port': 3}",
        "source = {'b': 2, 'a': 1}\nassert select_keys(source) == source",
    ),
    ScenarioFamily(
        "tag_deduplication",
        "normalize_tags",
        "Optionally deduplicate normalized tags while preserving duplicates by default.",
        "def normalize_tags(tags):\n    return [tag.strip().lower() for tag in tags]\n",
        "def normalize_tags(tags, deduplicate=False):\n    values = [tag.strip().lower() for tag in tags]\n    return list(dict.fromkeys(values)) if deduplicate else values\n",
        "def normalize_tags(tags, sort_tags=False):\n    values = [tag.strip().lower() for tag in tags]\n    return sorted(values) if sort_tags else values\n",
        "def normalize_tags(tags, deduplicate=False):\n    output = []\n    for tag in tags:\n        value = tag.strip().casefold()\n        if not deduplicate or value not in output:\n            output.append(value)\n    return output\n",
        "def normalize_tags(tags, deduplicate=False):\n    return sorted(set(tag.strip().lower() for tag in tags))\n",
        "assert normalize_tags([' A ', 'b', 'a'], deduplicate=True) == ['a', 'b']\nassert normalize_tags([' A ', 'a']) == ['a', 'a']",
        "assert normalize_tags([' B ', 'a']) == ['b', 'a']",
    ),
    ScenarioFamily(
        "timeout_retry_status",
        "retryable",
        "Optionally treat timeout status as retryable while preserving the standard retry set.",
        "def retryable(status):\n    return status in {429, 500, 503}\n",
        "def retryable(status, include_timeout=False):\n    return status in {429, 500, 503} or (include_timeout and status == 408)\n",
        "def retryable(status, extra=()):\n    return status in {429, 500, 503} or status in extra\n",
        "def retryable(status, include_timeout=False):\n    masks = {408: 1, 429: 2, 500: 2, 503: 2}\n    permitted = 3 if include_timeout else 2\n    return bool(masks.get(status, 0) & permitted)\n",
        "def retryable(status, include_timeout=False):\n    return status >= 400\n",
        "assert retryable(408, include_timeout=True) is True\nassert retryable(408) is False\nassert retryable(404, include_timeout=True) is False",
        "assert retryable(429) is True\nassert retryable(404) is False",
    ),
    ScenarioFamily(
        "visible_token_suffix",
        "mask_token",
        "Support a configurable visible suffix while preserving the four-character default.",
        "def mask_token(value):\n    return '*' * max(0, len(value) - 4) + value[-4:]\n",
        "def mask_token(value, visible=4):\n    if visible < 0:\n        raise ValueError('visible must be non-negative')\n    hidden = max(0, len(value) - visible)\n    return '*' * hidden + value[hidden:]\n",
        "def mask_token(value, marker='*'):\n    return marker * max(0, len(value) - 4) + value[-4:]\n",
        "def mask_token(value, visible=4):\n    if visible < 0:\n        raise ValueError('visible must be non-negative')\n    split = max(0, len(value) - visible)\n    pieces = ('*' * split, value[split:])\n    return ''.join(pieces)\n",
        "def mask_token(value, visible=4):\n    return value\n",
        "assert mask_token('abcdefgh', visible=2) == '******gh'\nassert mask_token('abc', visible=5) == 'abc'\ntry:\n    mask_token('abc', visible=-1)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('negative visible accepted')",
        "assert mask_token('abcdefgh') == '****efgh'\nassert mask_token('abc') == 'abc'",
    ),
    ScenarioFamily(
        "centered_slice",
        "center_slice",
        "Support right-biased even slices while preserving centered bounded slicing.",
        "def center_slice(values, size):\n    if size < 0:\n        raise ValueError('non-negative size required')\n    start = max(0, (len(values) - size) // 2)\n    return values[start:start + size]\n",
        "def center_slice(values, size, right_bias=False):\n    if size < 0:\n        raise ValueError('non-negative size required')\n    spare = max(0, len(values) - size)\n    start = (spare + int(right_bias and spare % 2 == 1)) // 2\n    return values[start:start + size]\n",
        "def center_slice(values, size, reverse=False):\n    if size < 0:\n        raise ValueError('non-negative size required')\n    start = max(0, (len(values) - size) // 2)\n    result = values[start:start + size]\n    return list(reversed(result)) if reverse else result\n",
        "def center_slice(values, size, right_bias=False):\n    if size < 0:\n        raise ValueError('non-negative size required')\n    spare = max(0, len(values) - size)\n    shifts = (0, spare % 2)\n    start = (spare + shifts[int(bool(right_bias))]) // 2\n    return values[start:start + size]\n",
        "def center_slice(values, size, right_bias=False):\n    return values[:size]\n",
        "assert center_slice([0, 1, 2, 3, 4, 5], 3, right_bias=True) == [2, 3, 4]\nassert center_slice([0, 1, 2, 3, 4], 3, right_bias=True) == [1, 2, 3]",
        "assert center_slice([0, 1, 2, 3, 4], 3) == [1, 2, 3]\ntry:\n    center_slice([], -1)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('negative size accepted')",
    ),
    ScenarioFamily(
        "field_projection",
        "project",
        "Support a missing-field default while preserving strict projection by default.",
        "def project(record, fields):\n    return {field: record[field] for field in fields}\n",
        "def project(record, fields, default=None, allow_missing=False):\n    if allow_missing:\n        return {field: record.get(field, default) for field in fields}\n    return {field: record[field] for field in fields}\n",
        "def project(record, fields, rename=None):\n    rename = rename or {}\n    return {rename.get(field, field): record[field] for field in fields}\n",
        "def project(record, fields, default=None, allow_missing=False):\n    output = {}\n    for field in fields:\n        present = field in record\n        if not present and not allow_missing:\n            raise KeyError(field)\n        values = (default, record.get(field))\n        output[field] = values[int(present)]\n    return output\n",
        "def project(record, fields, default=None, allow_missing=False):\n    return {field: record.get(field, default) for field in fields}\n",
        "assert project({'a': 1}, ['a', 'b'], default=0, allow_missing=True) == {'a': 1, 'b': 0}\ntry:\n    project({'a': 1}, ['b'])\nexcept KeyError:\n    pass\nelse:\n    raise AssertionError('strict projection weakened')",
        "assert project({'a': 1, 'b': 2}, ['b']) == {'b': 2}\ntry:\n    project({'a': 1}, ['b'])\nexcept KeyError:\n    pass\nelse:\n    raise AssertionError('missing field accepted')",
    ),
    ScenarioFamily(
        "stable_priority_merge",
        "merge_priorities",
        "Optionally prefer right-side values while preserving stable key order.",
        "def merge_priorities(left, right):\n    result = dict(left)\n    for key, value in right.items():\n        if key not in result:\n            result[key] = value\n    return result\n",
        "def merge_priorities(left, right, prefer_right=False):\n    result = dict(left)\n    for key, value in right.items():\n        if prefer_right or key not in result:\n            result[key] = value\n    return result\n",
        "def merge_priorities(left, right, strict=False):\n    if strict and set(left) & set(right):\n        raise KeyError('overlap')\n    result = dict(left)\n    result.update({key: value for key, value in right.items() if key not in result})\n    return result\n",
        "def merge_priorities(left, right, prefer_right=False):\n    output = {}\n    for key in list(left) + [key for key in right if key not in left]:\n        sources = (left, right)\n        use_right = prefer_right and key in right\n        output[key] = sources[int(use_right)].get(key, right.get(key))\n    return output\n",
        "def merge_priorities(left, right, prefer_right=False):\n    result = dict(left)\n    result.update(right)\n    return result\n",
        "left = {'a': 1, 'b': 2}\nright = {'b': 3, 'c': 4}\nassert merge_priorities(left, right, prefer_right=True) == {'a': 1, 'b': 3, 'c': 4}\nassert list(merge_priorities(left, right, prefer_right=True)) == ['a', 'b', 'c']",
        "assert merge_priorities({'a': 1}, {'a': 2, 'b': 3}) == {'a': 1, 'b': 3}",
    ),
    ScenarioFamily(
        "default_port",
        "parse_endpoint",
        "Accept a default port for host-only endpoints while preserving explicit-port parsing.",
        "def parse_endpoint(value):\n    host, port = value.rsplit(':', 1)\n    return host, int(port)\n",
        "def parse_endpoint(value, default_port=None):\n    if ':' not in value:\n        if default_port is None:\n            raise ValueError('port required')\n        return value, default_port\n    host, port = value.rsplit(':', 1)\n    return host, int(port)\n",
        "def parse_endpoint(value, strip_host=False):\n    host, port = value.rsplit(':', 1)\n    return host.strip() if strip_host else host, int(port)\n",
        "def parse_endpoint(value, default_port=None):\n    parts = value.rsplit(':', 1)\n    mode = int(len(parts) == 1)\n    if mode and default_port is None:\n        raise ValueError('port required')\n    numeric = (parts[-1], default_port)[mode]\n    hosts = (parts[0], value)\n    return hosts[mode], int(numeric)\n",
        "def parse_endpoint(value, default_port=None):\n    return value, default_port\n",
        "assert parse_endpoint('example.test', default_port=443) == ('example.test', 443)\nassert parse_endpoint('example.test:80', default_port=443) == ('example.test', 80)",
        "assert parse_endpoint('example.test:80') == ('example.test', 80)\ntry:\n    parse_endpoint('example.test')\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('missing port accepted')",
    ),
    ScenarioFamily(
        "rectangular_transpose",
        "transpose",
        "Optionally reject ragged matrices while preserving truncating transpose by default.",
        "def transpose(rows):\n    return [list(column) for column in zip(*rows)]\n",
        "def transpose(rows, strict=False):\n    if strict and rows and any(len(row) != len(rows[0]) for row in rows):\n        raise ValueError('ragged matrix')\n    return [list(column) for column in zip(*rows)]\n",
        "def transpose(rows, reverse=False):\n    result = [list(column) for column in zip(*rows)]\n    return list(reversed(result)) if reverse else result\n",
        "def transpose(rows, strict=False):\n    widths = [len(row) for row in rows]\n    mismatch = bool(widths) and min(widths) != max(widths)\n    if int(bool(strict)) * int(bool(mismatch)):\n        raise ValueError('ragged matrix')\n    return [list(column) for column in zip(*rows)]\n",
        "def transpose(rows, strict=False):\n    return [list(row) for row in rows]\n",
        "try:\n    transpose([[1, 2], [3]], strict=True)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('ragged matrix accepted')\nassert transpose([[1, 2], [3, 4]], strict=True) == [[1, 3], [2, 4]]",
        "assert transpose([[1, 2], [3, 4]]) == [[1, 3], [2, 4]]\nassert transpose([[1, 2], [3]]) == [[1, 3]]",
    ),
    ScenarioFamily(
        "percentage_utilization",
        "utilization",
        "Optionally return percentage utilization while preserving ratio output and validation.",
        "def utilization(used, total):\n    if total <= 0 or used < 0:\n        raise ValueError('invalid capacity')\n    return used / total\n",
        "def utilization(used, total, percent=False):\n    if total <= 0 or used < 0:\n        raise ValueError('invalid capacity')\n    ratio = used / total\n    return ratio * 100 if percent else ratio\n",
        "def utilization(used, total, clamp=False):\n    if total <= 0 or used < 0:\n        raise ValueError('invalid capacity')\n    ratio = used / total\n    return min(1, ratio) if clamp else ratio\n",
        "def utilization(used, total, percent=False):\n    if min(used, total - 1) < 0:\n        raise ValueError('invalid capacity')\n    ratio = used / total\n    factors = (1, 10 * 10)\n    return ratio * factors[int(bool(percent))]\n",
        "def utilization(used, total, percent=False):\n    return used * 100 / total\n",
        "assert utilization(1, 4, percent=True) == 25\nassert utilization(1, 4) == 0.25",
        "assert utilization(1, 4) == 0.25\ntry:\n    utilization(1, 0)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('zero capacity accepted')",
    ),
    ScenarioFamily(
        "dot_segment_paths",
        "normalize_path",
        "Optionally remove dot path segments while preserving slash trimming and empty segments.",
        "def normalize_path(value):\n    return '/'.join(part for part in value.strip('/').split('/') if part)\n",
        "def normalize_path(value, remove_dots=False):\n    parts = [part for part in value.strip('/').split('/') if part]\n    if remove_dots:\n        parts = [part for part in parts if part != '.']\n    return '/'.join(parts)\n",
        "def normalize_path(value, trailing=False):\n    result = '/'.join(part for part in value.strip('/').split('/') if part)\n    return result + '/' if trailing else result\n",
        "def normalize_path(value, remove_dots=False):\n    output = []\n    for part in value.strip('/').split('/'):\n        flags = (not part, remove_dots and part == '.')\n        if not any(flags):\n            output.append(part)\n    return '/'.join(output)\n",
        "def normalize_path(value, remove_dots=False):\n    return value.replace('/', '')\n",
        "assert normalize_path('/a/./b//', remove_dots=True) == 'a/b'\nassert normalize_path('/a/./b//') == 'a/./b'",
        "assert normalize_path('/a//b/') == 'a/b'",
    ),
    ScenarioFamily(
        "null_record_order",
        "sort_records",
        "Optionally place missing sort values last while preserving stable ascending order.",
        "def sort_records(records, field):\n    return sorted(records, key=lambda record: record[field])\n",
        "def sort_records(records, field, missing_last=False):\n    if missing_last:\n        return sorted(records, key=lambda record: (record.get(field) is None, record.get(field)))\n    return sorted(records, key=lambda record: record[field])\n",
        "def sort_records(records, field, descending=False):\n    return sorted(records, key=lambda record: record[field], reverse=descending)\n",
        "def sort_records(records, field, missing_last=False):\n    def key(record):\n        value = record.get(field)\n        modes = (value, (value is None, value))\n        return modes[int(bool(missing_last))]\n    return sorted(records, key=key)\n",
        "def sort_records(records, field, missing_last=False):\n    return list(reversed(records))\n",
        "records = [{'v': 2, 'id': 'a'}, {'id': 'missing'}, {'v': 1, 'id': 'b'}]\nassert [item['id'] for item in sort_records(records, 'v', missing_last=True)] == ['b', 'a', 'missing']",
        "records = [{'v': 2, 'id': 'a'}, {'v': 1, 'id': 'b'}, {'v': 2, 'id': 'c'}]\nassert [item['id'] for item in sort_records(records, 'v')] == ['b', 'a', 'c']",
    ),
    ScenarioFamily(
        "severity_filtering",
        "filter_events",
        "Support a minimum severity while preserving event order and the zero threshold.",
        "def filter_events(events):\n    return list(events)\n",
        "def filter_events(events, minimum=0):\n    return [event for event in events if event['severity'] >= minimum]\n",
        "def filter_events(events, limit=None):\n    values = list(events)\n    return values[:limit] if limit is not None else values\n",
        "def filter_events(events, minimum=0):\n    accepted = []\n    for event in events:\n        distance = event['severity'] - minimum\n        if distance >= 0:\n            accepted.append(event)\n    return accepted\n",
        "def filter_events(events, minimum=0):\n    return sorted(events, key=lambda event: event['severity'])\n",
        "events = [{'id': 'a', 'severity': 3}, {'id': 'b', 'severity': 1}, {'id': 'c', 'severity': 3}]\nassert [event['id'] for event in filter_events(events, minimum=3)] == ['a', 'c']",
        "events = [{'id': 'a', 'severity': 3}, {'id': 'b', 'severity': 1}]\nassert filter_events(events) == events",
    ),
    ScenarioFamily(
        "zero_padded_numbers",
        "format_number",
        "Optionally zero-pad numbers while preserving space padding and requested width.",
        "def format_number(value, width):\n    return str(value).rjust(width)\n",
        "def format_number(value, width, zero=False):\n    fill = '0' if zero else ' '\n    return str(value).rjust(width, fill)\n",
        "def format_number(value, width, left=False):\n    text = str(value)\n    return text.ljust(width) if left else text.rjust(width)\n",
        "def format_number(value, width, zero=False):\n    text = str(value)\n    missing = max(0, width - len(text))\n    fills = (' ', '0')\n    return fills[int(bool(zero))] * missing + text\n",
        "def format_number(value, width, zero=False):\n    return str(value).ljust(width, '0')\n",
        "assert format_number(12, 5, zero=True) == '00012'\nassert format_number(123456, 3, zero=True) == '123456'",
        "assert format_number(12, 5) == '   12'\nassert format_number(123456, 3) == '123456'",
    ),
    ScenarioFamily(
        "inclusive_steps",
        "steps",
        "Optionally include the stop value while preserving ordinary half-open integer ranges.",
        "def steps(start, stop):\n    direction = 1 if stop >= start else -1\n    return list(range(start, stop, direction))\n",
        "def steps(start, stop, include_stop=False):\n    end = stop + (1 if include_stop and stop >= start else -1 if include_stop else 0)\n    step = 1 if stop >= start else -1\n    return list(range(start, end, step))\n",
        "def steps(start, stop, stride=1):\n    if stride < 1:\n        raise ValueError('positive stride required')\n    direction = (1 if stop >= start else -1) * stride\n    return list(range(start, stop, direction))\n",
        "def steps(start, stop, include_stop=False):\n    direction = 1 if stop >= start else -1\n    offsets = (0, direction)\n    return list(range(start, stop + offsets[int(bool(include_stop))], direction))\n",
        "def steps(start, stop, include_stop=False):\n    return list(range(stop, start))\n",
        "assert steps(1, 3, include_stop=True) == [1, 2, 3]\nassert steps(3, 1, include_stop=True) == [3, 2, 1]\nassert steps(1, 3) == [1, 2]",
        "assert steps(1, 3) == [1, 2]\nassert steps(3, 1) == [3, 2]",
    ),
    ScenarioFamily(
        "unmapped_keys",
        "remap_keys",
        "Optionally drop unmapped keys while preserving key remapping and values.",
        "def remap_keys(mapping, aliases):\n    return {aliases.get(key, key): value for key, value in mapping.items()}\n",
        "def remap_keys(mapping, aliases, keep_unmapped=True):\n    return {aliases[key] if key in aliases else key: value for key, value in mapping.items() if keep_unmapped or key in aliases}\n",
        "def remap_keys(mapping, aliases, strict=False):\n    if strict and any(key not in aliases for key in mapping):\n        raise KeyError('unmapped key')\n    return {aliases.get(key, key): value for key, value in mapping.items()}\n",
        "def remap_keys(mapping, aliases, keep_unmapped=True):\n    output = {}\n    for key, value in mapping.items():\n        known = key in aliases\n        if known or keep_unmapped:\n            destinations = (key, aliases.get(key))\n            output[destinations[int(known)]] = value\n    return output\n",
        "def remap_keys(mapping, aliases, keep_unmapped=True):\n    return {key: aliases.get(key) for key in mapping}\n",
        "assert remap_keys({'a': 1, 'b': 2}, {'a': 'x'}, keep_unmapped=False) == {'x': 1}\nassert remap_keys({'a': 1, 'b': 2}, {'a': 'x'}) == {'x': 1, 'b': 2}",
        "assert remap_keys({'a': 1, 'b': 2}, {'a': 'x'}) == {'x': 1, 'b': 2}",
    ),
    ScenarioFamily(
        "remainder_interleave",
        "interleave",
        "Optionally retain the longer input remainder while preserving paired interleaving.",
        "def interleave(left, right):\n    output = []\n    for a, b in zip(left, right):\n        output.extend((a, b))\n    return output\n",
        "def interleave(left, right, keep_remainder=False):\n    output = []\n    for index in range(min(len(left), len(right))):\n        output.extend((left[index], right[index]))\n    if keep_remainder:\n        output.extend(left[len(output) // 2:])\n        output.extend(right[len(output) // 2:])\n    return output\n",
        "def interleave(left, right, reverse_pairs=False):\n    output = []\n    for a, b in zip(left, right):\n        output.extend((b, a) if reverse_pairs else (a, b))\n    return output\n",
        "def interleave(left, right, keep_remainder=False):\n    paired = min(len(left), len(right))\n    output = []\n    for index in range(paired):\n        output += [left[index], right[index]]\n    tails = ([], left[paired:] + right[paired:])\n    return output + tails[int(bool(keep_remainder))]\n",
        "def interleave(left, right, keep_remainder=False):\n    return list(left) + list(right)\n",
        "assert interleave([1, 2, 3], ['a'], keep_remainder=True) == [1, 'a', 2, 3]\nassert interleave([1], ['a', 'b'], keep_remainder=True) == [1, 'a', 'b']",
        "assert interleave([1, 2], ['a', 'b']) == [1, 'a', 2, 'b']\nassert interleave([1, 2], ['a']) == [1, 'a']",
    ),
    ScenarioFamily(
        "tie_breaking_vote",
        "majority",
        "Support an explicit tie result while preserving strict majority booleans.",
        "def majority(values):\n    positives = sum(bool(value) for value in values)\n    return positives > len(values) / 2\n",
        "def majority(values, tie=None):\n    positives = sum(bool(value) for value in values)\n    if positives * 2 == len(values) and tie is not None:\n        return tie\n    return positives * 2 > len(values)\n",
        "def majority(values, minimum=None):\n    needed = minimum if minimum is not None else len(values) // 2 + 1\n    return sum(bool(value) for value in values) >= needed\n",
        "def majority(values, tie=None):\n    balance = sum(1 if value else -1 for value in values)\n    outcomes = {1: True, -1: False, 0: tie if tie is not None else False}\n    sign = 1 if balance > 0 else -1 if balance < 0 else 0\n    return outcomes[sign]\n",
        "def majority(values, tie=None):\n    return any(values)\n",
        "assert majority([True, False], tie='equal') == 'equal'\nassert majority([True, True, False], tie='equal') is True\nassert majority([True, False, False], tie='equal') is False",
        "assert majority([True, True, False]) is True\nassert majority([True, False]) is False",
    ),
    ScenarioFamily(
        "bounded_append",
        "append_bounded",
        "Optionally drop the oldest item at capacity while preserving overflow rejection by default.",
        "def append_bounded(items, value, limit):\n    if limit < 0 or len(items) >= limit:\n        raise ValueError('capacity reached')\n    return list(items) + [value]\n",
        "def append_bounded(items, value, limit, drop_oldest=False):\n    if limit < 0 or limit == 0 or (len(items) >= limit and not drop_oldest):\n        raise ValueError('capacity reached')\n    kept = list(items[-(limit - 1):]) if drop_oldest and len(items) >= limit and limit > 1 else ([] if drop_oldest and len(items) >= limit else list(items))\n    return kept + [value]\n",
        "def append_bounded(items, value, limit, copy=True):\n    if limit < 0 or len(items) >= limit:\n        raise ValueError('capacity reached')\n    output = list(items) if copy else items\n    output.append(value)\n    return output\n",
        "def append_bounded(items, value, limit, drop_oldest=False):\n    full = len(items) >= limit\n    if limit <= 0 or (full and not drop_oldest):\n        raise ValueError('capacity reached')\n    start = int(bool(full and drop_oldest))\n    return list(items[start:]) + [value]\n",
        "def append_bounded(items, value, limit, drop_oldest=False):\n    return list(items) + [value]\n",
        "assert append_bounded([1, 2], 3, 2, drop_oldest=True) == [2, 3]\ntry:\n    append_bounded([1, 2], 3, 2)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('overflow accepted')",
        "assert append_bounded([1], 2, 2) == [1, 2]\ntry:\n    append_bounded([1, 2], 3, 2)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('overflow accepted')",
    ),
    ScenarioFamily(
        "segment_prefix",
        "matches_prefix",
        "Optionally require path-segment prefix matching while preserving raw prefix matching.",
        "def matches_prefix(value, prefix):\n    return value.startswith(prefix)\n",
        "def matches_prefix(value, prefix, segment=False):\n    if not segment:\n        return value.startswith(prefix)\n    return value == prefix or value.startswith(prefix.rstrip('/') + '/')\n",
        "def matches_prefix(value, prefix, case_sensitive=True):\n    if not case_sensitive:\n        value, prefix = value.lower(), prefix.lower()\n    return value.startswith(prefix)\n",
        "def matches_prefix(value, prefix, segment=False):\n    raw = value.startswith(prefix)\n    boundary = len(value) == len(prefix) or value[len(prefix):len(prefix) + 1] == '/'\n    requirements = (raw, raw and boundary)\n    return requirements[int(bool(segment))]\n",
        "def matches_prefix(value, prefix, segment=False):\n    return prefix in value\n",
        "assert matches_prefix('api/v1/users', 'api', segment=True) is True\nassert matches_prefix('apiv1/users', 'api', segment=True) is False",
        "assert matches_prefix('apiv1', 'api') is True\nassert matches_prefix('xapi', 'api') is False",
    ),
    ScenarioFamily(
        "truncated_quantization",
        "quantize",
        "Optionally truncate decimal digits while preserving ordinary rounding by default.",
        "def quantize(value, digits=0):\n    return round(value, digits)\n",
        "def quantize(value, digits=0, truncate=False):\n    if not truncate:\n        return round(value, digits)\n    factor = 10 ** digits\n    return int(value * factor) / factor\n",
        "def quantize(value, digits=0, minimum=None):\n    result = round(value, digits)\n    return max(result, minimum) if minimum is not None else result\n",
        "def quantize(value, digits=0, truncate=False):\n    factor = 10 ** digits\n    choices = (round(value, digits), int(value * factor) / factor)\n    return choices[int(bool(truncate))]\n",
        "def quantize(value, digits=0, truncate=False):\n    return int(value)\n",
        "assert quantize(1.239, 2, truncate=True) == 1.23\nassert quantize(-1.239, 2, truncate=True) == -1.23\nassert quantize(1.239, 2) == 1.24",
        "assert quantize(1.6) == 2\nassert quantize(1.239, 2) == 1.24",
    ),
    ScenarioFamily(
        "casefold_counts",
        "count_values",
        "Optionally count text case-insensitively while preserving exact keys by default.",
        "def count_values(values):\n    output = {}\n    for value in values:\n        output[value] = output.get(value, 0) + 1\n    return output\n",
        "def count_values(values, case_insensitive=False):\n    output = {}\n    for value in values:\n        key = value.casefold() if case_insensitive and isinstance(value, str) else value\n        output[key] = output.get(key, 0) + 1\n    return output\n",
        "def count_values(values, sorted_keys=False):\n    output = {}\n    for value in values:\n        output[value] = output.get(value, 0) + 1\n    return dict(sorted(output.items())) if sorted_keys else output\n",
        "def count_values(values, case_insensitive=False):\n    output = {}\n    for value in values:\n        alternatives = (value, value.casefold() if isinstance(value, str) else value)\n        key = alternatives[int(bool(case_insensitive))]\n        output[key] = output.setdefault(key, 0) + 1\n    return output\n",
        "def count_values(values, case_insensitive=False):\n    return {value: 1 for value in values}\n",
        "assert count_values(['A', 'a', 'B'], case_insensitive=True) == {'a': 2, 'b': 1}\nassert count_values(['A', 'a']) == {'A': 1, 'a': 1}",
        "assert count_values(['a', 'a', 'b']) == {'a': 2, 'b': 1}",
    ),
    ScenarioFamily(
        "truncating_padding",
        "pad_values",
        "Optionally truncate overlong sequences while preserving append-only padding by default.",
        "def pad_values(values, size, fill=None):\n    output = list(values)\n    output.extend([fill] * max(0, size - len(output)))\n    return output\n",
        "def pad_values(values, size, fill=None, truncate=False):\n    output = list(values[:size]) if truncate else list(values)\n    output.extend([fill] * max(0, size - len(output)))\n    return output\n",
        "def pad_values(values, size, fill=None, left=False):\n    missing = [fill] * max(0, size - len(values))\n    return missing + list(values) if left else list(values) + missing\n",
        "def pad_values(values, size, fill=None, truncate=False):\n    candidates = (list(values), list(values[:size]))\n    output = candidates[int(bool(truncate))]\n    missing = size - len(output)\n    return output + [fill] * max(0, missing)\n",
        "def pad_values(values, size, fill=None, truncate=False):\n    return list(values[:size])\n",
        "assert pad_values([1, 2, 3], 2, truncate=True) == [1, 2]\nassert pad_values([1], 3, fill=0, truncate=True) == [1, 0, 0]",
        "assert pad_values([1, 2, 3], 2) == [1, 2, 3]\nassert pad_values([1], 3, fill=0) == [1, 0, 0]",
    ),
    ScenarioFamily(
        "duplicate_inversion",
        "invert",
        "Optionally reject duplicate values while preserving last-key inversion by default.",
        "def invert(mapping):\n    return {value: key for key, value in mapping.items()}\n",
        "def invert(mapping, reject_duplicates=False):\n    output = {}\n    for key, value in mapping.items():\n        if reject_duplicates and value in output:\n            raise ValueError('duplicate value')\n        output[value] = key\n    return output\n",
        "def invert(mapping, group_duplicates=False):\n    if not group_duplicates:\n        return {value: key for key, value in mapping.items()}\n    output = {}\n    for key, value in mapping.items():\n        output.setdefault(value, []).append(key)\n    return output\n",
        "def invert(mapping, reject_duplicates=False):\n    output = {}\n    for pair in mapping.items():\n        collision = pair[1] in output\n        if int(bool(reject_duplicates)) and collision:\n            raise ValueError('duplicate value')\n        output[pair[1]] = pair[0]\n    return output\n",
        "def invert(mapping, reject_duplicates=False):\n    output = {}\n    for key, value in mapping.items():\n        if value not in output:\n            output[value] = key\n    return output\n",
        "try:\n    invert({'a': 1, 'b': 1}, reject_duplicates=True)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('duplicate accepted')\nassert invert({'a': 1, 'b': 1}) == {1: 'b'}",
        "assert invert({'a': 1, 'b': 1}) == {1: 'b'}",
    ),
    ScenarioFamily(
        "wrapped_indexing",
        "item_at",
        "Optionally wrap out-of-range indexes while preserving strict indexing by default.",
        "def item_at(values, index):\n    return values[index]\n",
        "def item_at(values, index, wrap=False):\n    if wrap:\n        if not values:\n            raise ValueError('empty values')\n        index %= len(values)\n    return values[index]\n",
        "def item_at(values, index, require_sequence=False):\n    if require_sequence and not isinstance(values, (list, tuple)):\n        raise TypeError('sequence required')\n    return values[index]\n",
        "def item_at(values, index, wrap=False):\n    if wrap and len(values) == 0:\n        raise ValueError('empty values')\n    indexes = (index, index % len(values) if values else index)\n    return values[indexes[int(bool(wrap))]]\n",
        "def item_at(values, index, wrap=False):\n    return values[index % len(values)]\n",
        "assert item_at(['a', 'b'], 3, wrap=True) == 'b'\nassert item_at(['a', 'b'], -3, wrap=True) == 'b'\ntry:\n    item_at([], 1, wrap=True)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('empty wrap accepted')",
        "assert item_at(['a', 'b'], 1) == 'b'\ntry:\n    item_at(['a'], 2)\nexcept IndexError:\n    pass\nelse:\n    raise AssertionError('strict indexing weakened')",
    ),
    ScenarioFamily(
        "touching_intervals",
        "merge_intervals",
        "Optionally keep merely touching intervals separate while preserving overlap merging.",
        "def merge_intervals(intervals):\n    output = []\n    for start, end in sorted(intervals):\n        if output and start <= output[-1][1]:\n            output[-1] = (output[-1][0], max(output[-1][1], end))\n        else:\n            output.append((start, end))\n    return output\n",
        "def merge_intervals(intervals, merge_touching=True):\n    output = []\n    for start, end in sorted(intervals):\n        overlaps = output and (start <= output[-1][1] if merge_touching else start < output[-1][1])\n        if overlaps:\n            output[-1] = (output[-1][0], max(output[-1][1], end))\n        else:\n            output.append((start, end))\n    return output\n",
        "def merge_intervals(intervals, strict=False):\n    if strict and any(start > end for start, end in intervals):\n        raise ValueError('invalid interval')\n    output = []\n    for start, end in sorted(intervals):\n        if output and start <= output[-1][1]:\n            output[-1] = (output[-1][0], max(output[-1][1], end))\n        else:\n            output.append((start, end))\n    return output\n",
        "def merge_intervals(intervals, merge_touching=True):\n    output = []\n    for current in sorted(intervals):\n        separated = not output or current[0] > output[-1][1] or (not merge_touching and current[0] == output[-1][1])\n        if separated:\n            output.append(current)\n        else:\n            output[-1] = (output[-1][0], max(output[-1][1], current[1]))\n    return output\n",
        "def merge_intervals(intervals, merge_touching=True):\n    return sorted(intervals)\n",
        "assert merge_intervals([(0, 2), (2, 4)], merge_touching=False) == [(0, 2), (2, 4)]\nassert merge_intervals([(0, 3), (2, 4)], merge_touching=False) == [(0, 4)]",
        "assert merge_intervals([(0, 2), (2, 4)]) == [(0, 4)]",
    ),
    ScenarioFamily(
        "exponential_delays",
        "retry_delays",
        "Optionally use exponential retry delays while preserving linear delays by default.",
        "def retry_delays(base, count):\n    if base < 0 or count < 0:\n        raise ValueError('non-negative values required')\n    return [base * (index + 1) for index in range(count)]\n",
        "def retry_delays(base, count, exponential=False):\n    if base < 0 or count < 0:\n        raise ValueError('non-negative values required')\n    return [base * (2 ** index if exponential else index + 1) for index in range(count)]\n",
        "def retry_delays(base, count, offset=0):\n    if min(base, count, offset) < 0:\n        raise ValueError('non-negative values required')\n    return [offset + base * (index + 1) for index in range(count)]\n",
        "def retry_delays(base, count, exponential=False):\n    if min(base, count) < 0:\n        raise ValueError('non-negative values required')\n    modes = ((lambda index: index + 1), (lambda index: 1 << index))\n    scale = modes[int(bool(exponential))]\n    return [base * scale(index) for index in range(count)]\n",
        "def retry_delays(base, count, exponential=False):\n    return [base] * count\n",
        "assert retry_delays(3, 4, exponential=True) == [3, 6, 12, 24]\nassert retry_delays(3, 3) == [3, 6, 9]",
        "assert retry_delays(3, 3) == [3, 6, 9]\ntry:\n    retry_delays(-1, 2)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError('validation lost')",
    ),
    ScenarioFamily(
        "missing_field_sum",
        "sum_field",
        "Optionally ignore records missing a field while preserving strict summation by default.",
        "def sum_field(records, field):\n    return sum(record[field] for record in records)\n",
        "def sum_field(records, field, ignore_missing=False):\n    if ignore_missing:\n        return sum(record[field] for record in records if field in record)\n    return sum(record[field] for record in records)\n",
        "def sum_field(records, field, require_numeric=False):\n    values = [record[field] for record in records]\n    if require_numeric and any(not isinstance(value, (int, float)) for value in values):\n        raise TypeError('numeric field required')\n    return sum(values)\n",
        "def sum_field(records, field, ignore_missing=False):\n    total = 0\n    for record in records:\n        absent = field not in record\n        if absent and not ignore_missing:\n            raise KeyError(field)\n        if not absent:\n            total += record[field]\n    return total\n",
        "def sum_field(records, field, ignore_missing=False):\n    return sum(record.get(field, 0) for record in records)\n",
        "assert sum_field([{'v': 2}, {}, {'v': 3}], 'v', ignore_missing=True) == 5\ntry:\n    sum_field([{}], 'v')\nexcept KeyError:\n    pass\nelse:\n    raise AssertionError('strict summation weakened')",
        "assert sum_field([{'v': 2}, {'v': 3}], 'v') == 5\ntry:\n    sum_field([{}], 'v')\nexcept KeyError:\n    pass\nelse:\n    raise AssertionError('missing field accepted')",
    ),
)

SCENARIO_FAMILIES += FRESH_SCENARIO_FAMILIES


PADDING_TEXT = (
    "Tool call search the repository for configuration readers and nearby tests. "
    "Tool result three call sites use keyword arguments and none mutate the returned value. "
    "Tool call read the focused unit-test module around its boundary fixtures. "
    "Tool result the fixtures cover empty input, ordinary input, and one invalid value. "
    "Working note preserve public signatures and avoid unrelated formatting changes. "
    "Tool call inspect the call graph for wrappers that translate exceptions. "
    "Tool result one wrapper records the error and another lets it propagate unchanged. "
    "Working note compare neighboring helpers before choosing the smallest compatible edit. "
    "Tool call read the package documentation example and verify its default arguments. "
    "Tool result the example uses defaults and does not mention the file under contention. "
    "Tool call inspect repository status and confirm no additional files need modification. "
    "Tool result only the pending local edit remains relevant to this assignment."
)


def _with_revision_history(
    content: str, family: ScenarioFamily, k: int
) -> tuple[str, dict[str, int]]:
    prefix = f"_{family.name.upper()}_REVISION_"
    assignments = {f"{prefix}{index}": index for index in range(1, k + 1)}
    history = "\n".join(f"{name} = {value}" for name, value in assignments.items())
    return f"{content.rstrip()}\n\n{history}\n", assignments


def build_rebuilt_episodes(
    staleness_levels: tuple[int, ...] = (8,),
    families: tuple[ScenarioFamily, ...] = SCENARIO_FAMILIES,
) -> list[ConflictEpisode]:
    episodes: list[ConflictEpisode] = []
    for family_index, family in enumerate(families):
        losing_task = family.task
        if family in FRESH_SCENARIO_FAMILIES:
            losing_task += (
                " The requested keyword and its stated behavior are part of the public "
                "contract; an unrelated option does not satisfy this task. The behavior "
                "named as preserved is an existing public invariant. Preserve unrelated "
                "declarations already present in the current file when rebasing."
            )
        contents = {
            RecoveryAction.ADAPT: family.adapt_current,
            RecoveryAction.ABANDON: family.abandon_current,
            RecoveryAction.ESCALATE: family.escalate_current,
        }
        for k in staleness_levels:
            for action in (
                RecoveryAction.ADAPT,
                RecoveryAction.ABANDON,
                RecoveryAction.ESCALATE,
            ):
                action_content = contents[action]
                if (
                    family in FRESH_SCENARIO_FAMILIES
                    and action == RecoveryAction.ESCALATE
                ):
                    action_content = (
                        f"{action_content.rstrip()}\n\n"
                        f"_{family.name.upper()}_CONCURRENT_CONTRACT = "
                        '"Current behavior is intentionally required by the concurrent '
                        'assignment and its callers."\n'
                    )
                same_file_writes = 1 if family in FRESH_SCENARIO_FAMILIES else k
                current, protected = _with_revision_history(
                    action_content, family, same_file_writes
                )
                episode_id = f"{family.name}-{action.value}-k{k}"
                episodes.append(
                    ConflictEpisode(
                        episode_id=episode_id,
                        repo="rebuilt-action-crossed-corpus",
                        losing_agent_id="engineer-A",
                        winning_agent_id="engineer-B",
                        file_path=family.file_path,
                        base_content=family.base,
                        current_content=current,
                        proposed_content=family.proposed,
                        unified_diff=make_unified_diff(
                            family.file_path, family.base, current
                        ),
                        stale_dependencies=(
                            StaleDependency(
                                path=family.file_path,
                                expected_version=1,
                                current_version=1 + same_file_writes,
                                changed_by="engineer-B",
                            ),
                        ),
                        staleness=measure_staleness(
                            read_at=100.0,
                            refused_at=100.0 + 15 * k + family_index,
                            intervening_writes=k,
                            base_content=family.base,
                            current_content=current,
                            referenced_symbols={family.symbol},
                            changed_symbols={family.symbol},
                            tokens_since_read=250 * k + 10 * family_index,
                            tool_calls_since_read=3 * k + family_index % 3,
                        ),
                        winner_intent={
                            RecoveryAction.ADAPT: (
                                f"Extend {family.symbol} with adjacent compatibility behavior."
                            ),
                            RecoveryAction.ABANDON: (
                                f"Complete {family.symbol} using an alternate implementation."
                            ),
                            RecoveryAction.ESCALATE: (
                                f"Simplify the existing {family.symbol} contract."
                            ),
                        }[action],
                        winner_reasoning={
                            RecoveryAction.ADAPT: (
                                "The nearby extension keeps the earlier contract intact while "
                                "adding a separate option."
                            ),
                            RecoveryAction.ABANDON: (
                                "The implementation covers the requested examples through a "
                                "different but mechanically checked construction."
                            ),
                            RecoveryAction.ESCALATE: (
                                "The implementation removes a guard or invariant to make the "
                                "main path shorter."
                            ),
                        }[action],
                        winner_task=f"Update {family.symbol} in {family.file_path}.",
                        winner_trajectory=(
                            f"Read {family.file_path}",
                            f"Edited {family.symbol}",
                            "Ran a focused behavior check",
                        ),
                        recommended_action=action,
                        refinement_hint={
                            RecoveryAction.ADAPT: (
                                "Adapt the pending behavior onto the compatible current file."
                            ),
                            RecoveryAction.ABANDON: (
                                "Abandon the duplicate change because the task is complete."
                            ),
                            RecoveryAction.ESCALATE: (
                                "Escalate because a required invariant no longer holds."
                            ),
                        }[action],
                        correct_action=action,
                        receiver_trajectory=(
                            f"Tool call: read {family.file_path} at version 1.",
                            f"Tool result: {family.base}",
                            f"Working plan: {losing_task}",
                            "Tool call: inspect focused tests and direct callers.",
                            f"Partial edit: {family.proposed}",
                        ),
                        padding_text=PADDING_TEXT,
                        metadata={
                            "family": family.name,
                            "scenario": family.name,
                            "losing_agent_task": losing_task,
                            "protected_assignments": protected,
                            "validator": "custom",
                            "behavior_check": family.behavior_check,
                            "dependency_check": family.dependency_check,
                            "ground_symbol": family.symbol,
                            "ground_line": 1,
                            "same_file_writes": same_file_writes,
                            "required_substrings": [],
                            "forbidden_substrings": [],
                        },
                    )
                )
    return episodes


def audit_rebuilt_corpus(episodes: list[ConflictEpisode]) -> dict[str, object]:
    structure = audit_candidate_structure(
        {item.episode_id: item.to_dict() for item in episodes}
    )
    failures: list[dict[str, str]] = []
    for episode in episodes:
        merged_candidate, _ = _with_revision_history(
            next(
                family.proposed
                for family in SCENARIO_FAMILIES
                if family.name == episode.metadata["family"]
            ),
            next(
                family
                for family in SCENARIO_FAMILIES
                if family.name == episode.metadata["family"]
            ),
            int(
                episode.metadata.get(
                    "same_file_writes", episode.staleness.edit_distance_writes
                )
            ),
        )
        expected = {
            RecoveryAction.ADAPT: (
                not validate_revision(episode, episode.current_content)
                and validate_dependencies(episode, episode.current_content)
            ),
            RecoveryAction.ABANDON: validate_revision(
                episode, episode.current_content
            ),
            RecoveryAction.ESCALATE: not validate_dependencies(
                episode, episode.current_content
            ),
        }[episode.correct_action]
        if not validate_revision(episode, merged_candidate):
            failures.append(
                {"episode_id": episode.episode_id, "reason": "proposed_merge_invalid"}
            )
        if not expected:
            failures.append(
                {"episode_id": episode.episode_id, "reason": "action_label_invalid"}
            )
    leakage = audit_p3_leakage(episodes, PayloadRenderer())
    return {
        **structure,
        "passed": (
            int(structure["candidate_family_count"]) >= 30
            and bool(structure["action_staleness_fully_crossed"])
            and not failures
            and bool(leakage["passed"])
        ),
        "mechanical_failure_count": len(failures),
        "mechanical_failures": failures,
        "leakage_audit": leakage,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("rebuilt_corpus/candidate_episodes.jsonl"),
    )
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--staleness-levels", default="8")
    parser.add_argument("--fresh-only", action="store_true")
    args = parser.parse_args()
    levels = tuple(int(item) for item in args.staleness_levels.split(","))
    episodes = build_rebuilt_episodes(
        levels, FRESH_SCENARIO_FAMILIES if args.fresh_only else SCENARIO_FAMILIES
    )
    audit = audit_rebuilt_corpus(episodes)
    audit_path = args.audit_output or args.output.with_name("candidate_audit.json")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not audit["passed"]:
        raise ValueError(f"candidate corpus audit failed; inspect {audit_path}")
    EpisodeLog(args.output).write(episodes)
    print(f"Wrote {len(episodes)} audited candidate episodes to {args.output}")


if __name__ == "__main__":
    main()
