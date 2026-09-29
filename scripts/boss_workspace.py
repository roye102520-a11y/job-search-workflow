"""Persist user-supplied BOSS screening inputs inside one private career case.

This module never accesses BOSS. Saved rows are leads for review, not a record of
an application or a verified live vacancy.
"""

import json
import os
import tempfile
from datetime import datetime, timezone

from boss_assist import (DEFAULT_CONFIG, FIELDS, evaluate_jobs, import_blocked_companies,
                         parse_jobs_text, stable_boss_id, validate_config)
from career_workspace import local_file, preferences, read_json


MAX_UI_JOBS = 500
SETTINGS_FILE = 'boss-settings.json'
JOBS_FILE = 'boss-jobs.json'


def _write_json(case, name, payload):
    """Replace a case file atomically so interrupted saves preserve old data."""
    target = local_file(case, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                         prefix=f'.{name}.', suffix='.tmp', delete=False)
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, target)
    finally:
        if os.path.exists(handle.name):
            os.unlink(handle.name)


def settings(case):
    saved = read_json(case, SETTINGS_FILE, None)
    if saved is not None:
        return validate_config(saved)
    prior = preferences(case)
    defaults = dict(DEFAULT_CONFIG)
    defaults['cities'] = prior.get('locations', [])
    defaults['excluded_companies'] = prior.get('excluded_companies', [])
    return validate_config(defaults)


def _saved_jobs(case):
    saved = read_json(case, JOBS_FILE, None)
    if saved is None:
        return None
    if not isinstance(saved, dict) or not isinstance(saved.get('jobs'), list):
        raise ValueError('已导入的 BOSS 岗位文件格式错误')
    rows = saved['jobs']
    if len(rows) > MAX_UI_JOBS or any(not isinstance(row, dict) for row in rows):
        raise ValueError('已导入的 BOSS 岗位超出工作台限制')
    return saved


def state(case):
    config = settings(case)
    saved = _saved_jobs(case)
    result = evaluate_jobs(saved['jobs'], config) if saved is not None else None
    return {'settings': config, 'screen': result,
            'imported_at': saved.get('imported_at') if saved else None,
            'job_count': len(saved['jobs']) if saved else 0,
            'source': 'user_supplied_local_import', 'automated_actions': False}


def save_settings(case, request):
    if not isinstance(request, dict) or set(request) != {'settings'}:
        raise ValueError('筛选设置请求格式错误')
    clean = validate_config(request['settings'])
    _write_json(case, SETTINGS_FILE, clean)
    return state(case)


def import_blocked(case, request):
    if not isinstance(request, dict) or set(request) != {'data'}:
        raise ValueError('屏蔽公司导入请求格式错误')
    data = request['data']
    if not isinstance(data, str) or len(data) > 30000:
        raise ValueError('屏蔽公司文字超过限制')
    added = import_blocked_companies(data)
    config = settings(case)
    config['excluded_companies'] = list(dict.fromkeys(config['excluded_companies'] + added))
    clean = validate_config(config)
    _write_json(case, SETTINGS_FILE, clean)
    result = state(case)
    result['imported_companies'] = len(added)
    return result


def screen_jobs(case, request):
    if not isinstance(request, dict) or set(request) != {'data'}:
        raise ValueError('岗位导入请求格式错误')
    data = request['data']
    if not isinstance(data, str) or not data.strip() or len(data.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError('请提供 2 MB 以内的 JSON 或 CSV 岗位内容')
    rows = parse_jobs_text(data)
    if len(rows) > MAX_UI_JOBS:
        raise ValueError(f'工作台一次最多导入 {MAX_UI_JOBS} 条岗位')
    # Keep a stable public detail path, not BOSS session parameters, in the
    # private on-disk queue as well as in the response shown by the UI.
    cleaned_rows = []
    for row in rows:
        clean_row = dict(row)
        for alias in FIELDS['url']:
            value = clean_row.get(alias)
            stable_id = stable_boss_id(value) if isinstance(value, str) else None
            if stable_id:
                clean_row[alias] = f'https://www.zhipin.com/job_detail/{stable_id}.html'
                break
        cleaned_rows.append(clean_row)
    result = evaluate_jobs(cleaned_rows, settings(case))
    _write_json(case, JOBS_FILE, {'imported_at': datetime.now(timezone.utc).isoformat(), 'jobs': cleaned_rows})
    return {'settings': settings(case), 'screen': result,
            'imported_at': read_json(case, JOBS_FILE, {})['imported_at'],
            'job_count': len(cleaned_rows), 'source': 'user_supplied_local_import',
            'automated_actions': False}
