#!/usr/bin/env python3
"""Local-only job records: validate, register, journal attempts and review cohorts.
Python 3.9+, standard library. Does not submit applications or verify user consent.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import fcntl

STAGES = set('discovered shortlisted preparing ready submitted assessment interview offer rejected withdrawn closed'.split())
EXEC = {'idle', 'filling', 'blocked', 'submission_unknown'}
SYNC = {'not_requested', 'pending', 'synced', 'failed'}
FIELDS = 'job_key company role role_family resume_variant location url status execution_status sync_status resume_path submitted_at updated_at receipt_path next_action'.split()

def require(test, message):
    if not test:
        raise ValueError(message)

def now():
    return datetime.now(timezone.utc).isoformat()

def stamp(value):
    require(isinstance(value, str) and value.strip(), 'Timestamp must be a nonempty ISO 8601 string')
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(d.tzinfo is not None, 'Timestamp requires timezone')
    return d

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def canonical(url):
    require(isinstance(url, str) and url.strip(), 'Job URL must be a nonempty string')
    u = urlsplit(url.strip())
    require(u.scheme in ('https', 'http') and u.netloc, 'Invalid job URL')
    query = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('gclid', 'fbclid', 'trid')]
    return urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path.rstrip('/'), urlencode(sorted(query)), ''))

def local(root, value):
    require(isinstance(value, str) and value, 'Empty file path')
    p = (root / value).resolve()
    require(p.is_relative_to(root.resolve()), 'File must be inside case: ' + value)
    require(p.is_file(), 'Missing file: ' + value)
    return p

def read_json(p):
    return json.loads(p.read_text(encoding='utf-8'))

def atomic(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=p.parent, prefix='.job-data-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, p)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

@contextmanager
def lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.job-data.lock').open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

def rows(root):
    p = root / 'application-tracker.csv'
    if not p.exists():
        return [], FIELDS.copy()
    with p.open(encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f)
        data, names = list(r), list(r.fieldnames or [])
    require('job_key' in names, 'Existing CSV requires explicit job_key migration')
    keys = [row.get('job_key') for row in data]
    require(all(isinstance(key, str) and key.strip() for key in keys), 'Existing CSV contains empty job_key; migrate explicitly')
    require(len(keys) == len(set(keys)), 'Duplicate tracker key; repair existing CSV before updating records')
    for row in data:
        if 'application_status' in row:
            require(not row.get('status') or row['status'] == row['application_status'], 'Conflicting stage aliases')
            row['status'] = row['application_status']
    return data, list(dict.fromkeys(names + FIELDS))

def save_rows(root, data, fields):
    import io
    out = io.StringIO(newline='')
    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()
    for row in data:
        if 'application_status' in fields:
            row['application_status'] = row.get('status', '')
        w.writerow(row)
    atomic(root / 'application-tracker.csv', out.getvalue())

def events(root):
    p = root / 'application-events.jsonl'
    return [json.loads(s) for s in p.read_text().splitlines() if s.strip()] if p.exists() else []

def append(root, event):
    p = root / 'application-events.jsonl'
    with p.open('a', encoding='utf-8') as f:
        f.write(json.dumps(event, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())

def manifests(root):
    return [(p, read_json(p)) for p in sorted(root.glob('applications/*/manifest.json'))]

def validate(root, m, final=False):
    require(isinstance(m, dict), 'Manifest must be a JSON object')
    require(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,119}', m.get('job_key', '')), 'Unsafe job_key')
    require(m.get('status') in STAGES, 'Invalid stage')
    require(m.get('execution_status', 'idle') in EXEC, 'Invalid execution status')
    require(m.get('sync_status', 'not_requested') in SYNC, 'Invalid sync status')
    for k in ('company', 'role', 'role_family', 'resume_variant', 'url', 'jd_path', 'resume_path'):
        require(isinstance(m.get(k), str) and m[k].strip(), 'Missing ' + k)
    canonical(m['url'])
    require(isinstance(m.get('aliases', []), list), 'Aliases must be a list of URLs')
    for value in m.get('aliases', []):
        canonical(value)
    require(isinstance(m.get('evidence_refs'), list) and m['evidence_refs'], 'Missing evidence references')
    for ref in m['evidence_refs']:
        require(isinstance(ref, str) and ref.strip(), 'Evidence reference must be a nonempty path string')
        local(root, ref.split('#')[0])
    for k in ('jd_path', 'resume_path', 'email_path', 'cover_letter_path'):
        if m.get(k):
            local(root, m[k])
    require(isinstance(m.get('artifacts', []), list), 'Artifacts must be a list')
    for a in m.get('artifacts', []):
        require(isinstance(a, dict), 'Artifact must be an object with path and sha256')
        require(digest(local(root, a['path'])) == a['sha256'], 'Attachment hash mismatch: ' + a['path'])
    if final:
        require(m['status'] == 'ready', 'Application is not ready')
        require(m.get('unresolved_required_fields') == [], 'Unresolved required fields')
        require(m.get('authorization_scope', '').strip(), 'Missing actual authorization reference')
        require(m.get('channel') in ('email', 'web'), 'Invalid channel')
        require(m.get('recipient_or_endpoint', '').strip(), 'Missing recipient/endpoint')
        require(m.get('artifacts'), 'Missing hashed artifacts')
        require(any(a['path'] == m['resume_path'] for a in m['artifacts']), 'Resume missing from artifacts')
    return True

def duplicate(root, m):
    urls = {canonical(u) for u in [m['url']] + m.get('aliases', [])}
    ident = (m.get('employer_namespace'), m.get('requisition_id'))
    for _, other in manifests(root):
        if other['job_key'] == m['job_key']:
            prior_id = (other.get('employer_namespace'), other.get('requisition_id'))
            require(not (all(ident) and all(prior_id)) or ident == prior_id, 'Same job_key has conflicting requisition IDs')
            continue
        same_id = all(ident) and ident == (other.get('employer_namespace'), other.get('requisition_id'))
        same_url = urls.intersection(canonical(u) for u in [other['url']] + other.get('aliases', []))
        require(not (same_id or same_url), 'Duplicate job: ' + other['job_key'])
    data, _ = rows(root)
    for row in data:
        if row['job_key'] != m['job_key'] and row.get('url'):
            require(canonical(row['url']) not in urls, 'Duplicate tracker URL: ' + row['job_key'])
    require(sum(r['job_key'] == m['job_key'] for r in data) <= 1, 'Duplicate tracker key')

def upsert(root, m):
    validate(root, m)
    duplicate(root, m)
    data, fields = rows(root)
    old = next((r for r in data if r['job_key'] == m['job_key']), None)
    if old is None:
        old = {'job_key': m['job_key']}
        data.append(old)
    protected = bool(old.get('submitted_at')) or old.get('status') in {'submitted','assessment','interview','offer','rejected','withdrawn','closed'}
    for k in FIELDS:
        if k in m and k not in {'status', 'submitted_at', 'receipt_path', 'execution_status', 'sync_status'}:
            if not protected or k not in {'role_family', 'resume_variant', 'resume_path'}:
                old[k] = m[k]
    if not protected:
        require(m['status'] in {'discovered','shortlisted','preparing','ready','closed'}, 'Use observed events for outcomes')
        old['status'] = m['status']
    old.setdefault('execution_status', 'idle')
    old.setdefault('sync_status', 'not_requested')
    old['updated_at'] = now()
    save_rows(root, data, fields)

def check_start_allowed(root, m):
    validate(root, m, final=True)
    duplicate(root, m)
    log = events(root)
    started = [e for e in log if e['job_key'] == m['job_key'] and e['action'] == 'attempt_started']
    for e in started:
        results = [x for x in log if x.get('attempt_id') == e['attempt_id'] and x['action'] == 'attempt_result']
        require(results and results[-1]['result'] == 'not_submitted', 'Prior attempt exists or is unresolved; do not resubmit')
    data, _ = rows(root)
    r = next((r for r in data if r['job_key'] == m['job_key']), {})
    require(not r.get('submitted_at') and r.get('status') not in {'submitted','assessment','interview','offer','rejected','withdrawn','closed'}, 'Already submitted or closed; review reapplication separately')
    require(r.get('execution_status') != 'submission_unknown', 'Unresolved tracker submission')

def start(root, m):
    check_start_allowed(root, m)
    attempt = str(uuid.uuid4())
    folder = root / 'applications' / m['job_key'] / 'attempts' / attempt
    folder.mkdir(parents=True)
    frozen = []
    for i, a in enumerate(m['artifacts']):
        source = local(root, a['path'])
        content = source.read_bytes()
        require(hashlib.sha256(content).hexdigest() == a['sha256'], 'Attachment changed during snapshot')
        dest = folder / (str(i) + '-' + source.name)
        dest.write_bytes(content)
        frozen.append({'path': str(dest.relative_to(root)), 'sha256': a['sha256'], 'source_path': a['path']})
    append(root, dict(event_id=str(uuid.uuid4()), attempt_id=attempt, job_key=m['job_key'], timestamp=now(),
        action='attempt_started', result='pending', source='local_preparation', artifacts=frozen,
        role_family=m['role_family'], resume_variant=m['resume_variant'],
        resume_snapshot_path=next(a['path'] for a in frozen if a['source_path'] == m['resume_path']),
        channel=m['channel'], recipient_or_endpoint=m['recipient_or_endpoint'], authorization_scope=m['authorization_scope']))
    return {'attempt_id': attempt, 'artifacts': frozen, 'note': 'Not submitted. Use frozen artifacts for the external action.'}

def record(root, event):
    require(isinstance(event, dict), 'Event must be a JSON object')
    require(event.get('source') in {'user_report','tool_observation'}, 'Invalid observation source')
    require(event.get('action') in {'attempt_result','reply','assessment','interview','offer','rejected','withdrawn','outreach','followup'}, 'Invalid event action')
    stamp(event['timestamp'])
    require(stamp(event['timestamp']) <= datetime.now(timezone.utc) + timedelta(minutes=5), 'Future observation timestamp')
    local(root, event['evidence_path'])
    log = events(root)
    require(event.get('event_id'), 'Stable event_id required for idempotent retry')
    existing = next((e for e in log if e['event_id'] == event['event_id']), None)
    if existing:
        require(existing == event, 'Conflicting duplicate event_id')
        return
    require(any(r['job_key'] == event.get('job_key') for r in rows(root)[0]), 'Register job first')
    if event.get('attempt_id') is not None:
        require(isinstance(event['attempt_id'], str) and event['attempt_id'].strip(), 'attempt_id must be a nonempty string when supplied')
        linked = next((e for e in log if e['action'] == 'attempt_started' and e.get('attempt_id') == event['attempt_id']), None)
        require(linked and linked['job_key'] == event['job_key'], 'No matching started attempt for this job')
    prior_job = [e for e in log if e['job_key'] == event['job_key']]
    require(not prior_job or stamp(event['timestamp']) >= max(stamp(e['timestamp']) for e in prior_job),
            'Observation time precedes existing events; timestamp is observation time, not recalled occurrence time')
    if event['action'] == 'attempt_result':
        require(event.get('result') in {'submitted','not_submitted','unknown'}, 'Invalid result')
        start_event = next((e for e in log if e['action'] == 'attempt_started' and e['attempt_id'] == event.get('attempt_id')), None)
        require(start_event and start_event['job_key'] == event['job_key'], 'No matching started attempt')
        prior = [e for e in log if e['action'] == 'attempt_result' and e.get('attempt_id') == event['attempt_id']]
        require(not prior or prior[-1]['result'] == 'unknown', 'Attempt already has a final result')
        if event.get('occurred_at'):
            require(stamp(event['occurred_at']) <= stamp(event['timestamp']), 'Occurrence cannot follow observation')
        if event['result'] == 'submitted':
            for artifact in start_event['artifacts']:
                require(digest(local(root, artifact['path'])) == artifact['sha256'], 'Frozen attachment was modified')
    append(root, event)

def reconcile(root):
    data, fields = rows(root)
    log = events(root)
    starts = {e['attempt_id']: e for e in log if e['action'] == 'attempt_started'}
    later_stages = {'assessment','interview','offer','rejected','withdrawn','closed'}
    for e in log:
        r = next((r for r in data if r['job_key'] == e['job_key']), None)
        require(r is not None, 'Event has no tracker row')
        action = e['action']
        if action == 'attempt_started':
            r['execution_status'] = 'submission_unknown'
        elif action == 'attempt_result':
            r['execution_status'] = 'submission_unknown' if e['result'] == 'unknown' else 'idle'
            if e['result'] == 'submitted':
                if r.get('status') not in later_stages:
                    r['status'] = 'submitted'
                r['submitted_at'] = e.get('occurred_at', '')
                r['receipt_path'] = e['evidence_path']
                started = starts.get(e['attempt_id'], {})
                for field in ('role_family', 'resume_variant'):
                    if started.get(field):
                        r[field] = started[field]
                if started.get('resume_snapshot_path'):
                    r['resume_path'] = started['resume_snapshot_path']
                else:
                    r['next_action'] = 'Verify submitted attachment from attempt artifacts; legacy event has no explicit resume mapping'
        elif action in {'assessment','interview','offer','rejected','withdrawn'}:
            r['status'] = action
        r['updated_at'] = e['timestamp']
    save_rows(root, data, fields)

def report(root, as_of, days, min_age):
    end = stamp(as_of)
    start_at = end - timedelta(days=days)
    log = [e for e in events(root) if stamp(e['timestamp']) <= end]
    groups = defaultdict(lambda: dict(submitted=0, mature=0, replies=0, interviews=0, offers=0, pending=0))
    unknown = set()
    seen = set()
    for e in log:
        if e['action'] != 'attempt_result' or e['result'] != 'submitted':
            continue
        key = e['job_key']
        if key in seen:
            continue
        seen.add(key)
        if not e.get('occurred_at'):
            unknown.add(key)
            continue
        at = stamp(e['occurred_at'])
        if not start_at <= at <= end:
            continue
        begin = next(x for x in log if x['action'] == 'attempt_started' and x['attempt_id'] == e['attempt_id'])
        g = groups[(begin.get('role_family','unknown'), begin.get('resume_variant','unknown'))]
        g['submitted'] += 1
        if end - at < timedelta(days=min_age):
            continue
        g['mature'] += 1
        follow = {x['action'] for x in log if x['job_key'] == key
                  and stamp(x['timestamp']) >= stamp(begin['timestamp'])
                  and (not x.get('attempt_id') or x['attempt_id'] == e['attempt_id'])}
        replied = bool(follow & {'reply','assessment','interview','offer','rejected'})
        interviewed = bool(follow & {'interview','offer'})
        g['replies'] += int(replied)
        g['interviews'] += int(interviewed)
        g['offers'] += int('offer' in follow)
        g['pending'] += int(not replied and not follow & {'withdrawn'})
    out = ['# 分方向与简历版本复盘', '', f'窗口：{start_at.isoformat()} 至 {end.isoformat()}；观察期至少 {min_age} 天。',
           '按岗位去重；分母为窗口内且已过观察期的确认投递。回复含拒信/测评，不等于积极回复；Offer 计作曾到达面试。',
           '按提交时的岗位方向和简历版本归组；不将新版草稿归因给旧投递。用户报告/工具观察均保留证据，脚本不独立验证真实性。', '',
           '| 方向 | 简历版本 | 已投 | 可观察 | 回复率 | 面试率 | Offer数 | 未回复 |',
           '|---|---|---:|---:|---:|---:|---:|---:|']
    for (role, version), g in sorted(groups.items()):
        n = g['mature']
        rate = lambda k: f"{g[k]}/{n} ({g[k]/n:.0%})" if n else 'N/A'
        esc = lambda s: s.replace('|', '\\|').replace('\n', ' ')
        out.append(f"| {esc(role)} | {esc(version)} | {g['submitted']} | {n} | {rate('replies')} | {rate('interviews')} | {g['offers']} | {g['pending']} |")
    if not groups:
        out += ['', '暂无窗口内的已确认投递，无法判断方向或简历版本优劣。准备中的材料不计入分母。']
    legacy = {r['job_key'] for r in rows(root)[0] if r.get('submitted_at') or r.get('status') in {'submitted','assessment','interview','offer'}} - seen
    out += ['', f'投递日期未知、未进入时间窗口统计：{len(unknown)} 个岗位。',
            f'Tracker 显示投递/后续阶段但缺少事件证据、未纳入本报告：{len(legacy)} 个岗位。需按真实记录迁移，不能补造 started 或时间。',
            '少于 10 个可观察样本的分组仅列数，不作排名；即使样本更多，方向/公司/资历差异也会混淆结果，不能据此证明简历版本的因果效果。']
    return '\n'.join(out) + '\n'

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', required=True, type=Path)
    s = p.add_subparsers(dest='cmd', required=True)
    for name in ('validate','register','start'):
        q = s.add_parser(name)
        q.add_argument('--manifest', required=True, type=Path)
    q = s.add_parser('record'); q.add_argument('--event', required=True, type=Path)
    s.add_parser('reconcile')
    q = s.add_parser('report')
    q.add_argument('--as-of', default=now()); q.add_argument('--days', type=int, default=90)
    q.add_argument('--min-age', type=int, default=14); q.add_argument('--output', required=True, type=Path)
    a = p.parse_args(); root = a.case.resolve()
    try:
        if a.cmd == 'validate':
            m = read_json(a.manifest); validate(root, m); duplicate(root, m)
            print('Manifest, paths, hashes and exact duplicate checks passed. Content/consent not verified.')
        elif a.cmd == 'report':
            require(a.days > 0 and a.min_age >= 0, 'Invalid reporting interval')
            with lock(root):
                result = report(root, a.as_of, a.days, a.min_age)
            atomic(a.output, result); print(a.output)
        else:
            with lock(root):
                if a.cmd == 'register':
                    upsert(root, read_json(a.manifest))
                elif a.cmd == 'start':
                    m = read_json(a.manifest); check_start_allowed(root, m); upsert(root, m)
                    print(json.dumps(start(root, m), ensure_ascii=False))
                    reconcile(root)
                elif a.cmd == 'record':
                    record(root, read_json(a.event)); reconcile(root)
                else:
                    reconcile(root)
            print('Local records updated; no external action performed.')
    except (ValueError, KeyError, OSError, TypeError) as e:
        print('ERROR: ' + str(e), file=sys.stderr); return 2
    return 0

if __name__ == '__main__':
    sys.exit(main())
