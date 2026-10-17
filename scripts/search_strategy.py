"""Local batch triage, shared gaps and evidence-based follow-up drafts.

Uses the existing case and requirement engine. Never fetches, sends or changes
application stages. Scores measure rule-recognised evidence, not hiring odds.
"""
import argparse
import json
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from career_workspace import local_file, read_json, safe_url
from jd_requirements import assess
from resume_pipeline import canonical_job_url, load_evidence


def job_url_key(value):
    # Hash routers often put the requisition ID after '#'. Retain it rather
    # than silently merging separate jobs hosted on the same careers page.
    return canonical_job_url(value) + (urlsplit(value.strip()).fragment,)


def calendar_day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def event_time(value):
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp.astimezone(timezone.utc) if stamp.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def tracker(case):
    path = local_file(case, 'application-tracker.csv')
    if not path.exists():
        return []
    from job_data import rows
    return rows(Path(case))[0]


def rank_jobs(case, request, today=None):
    today = today or date.today()
    if not isinstance(request, dict) or set(request) != {'jobs'}:
        raise ValueError('请提供 jobs 岗位数组')
    jobs = request['jobs']
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= 100:
        raise ValueError('每次需要 1–100 个岗位')
    evidence = load_evidence(Path(case))
    existing = tracker(case)
    tracked = {job_url_key(r['url']) for r in existing if safe_url(r.get('url'))}
    preferences = read_json(case, 'search-preferences.json', {})
    if not isinstance(preferences, dict) or not isinstance(preferences.get('excluded_companies', []), list):
        raise ValueError('岗位偏好或排除公司名单格式错误')
    excluded = {str(x).strip().casefold() for x in preferences.get('excluded_companies', [])}
    seen, results = {}, []
    for index, job in enumerate(jobs):
        allowed = {'company', 'title', 'url', 'jd', 'deadline', 'posted_date'}
        if not isinstance(job, dict) or set(job) - allowed or any(not isinstance(v, str) for v in job.values()):
            raise ValueError('每个岗位只接受 company/title/url/jd/deadline/posted_date 文字字段')
        if any(len(v) > (50000 if k == 'jd' else 2048) for k, v in job.items()):
            raise ValueError('岗位文字过长')
        if any(not job.get(k, '').strip() for k in ('company', 'title')):
            raise ValueError('请为每个岗位填写 company 和 title')
        row = {**job, 'id': str(index + 1), 'status': 'review', 'warnings': [], 'requirements': [], 'score': None}
        url = job.get('url', '')
        if url and not safe_url(url):
            raise ValueError('岗位网址必须是无账号密码的 HTTP/HTTPS 链接')
        key = job_url_key(url) if url else None
        # No fuzzy company/title merging: identical titles may be different jobs.
        if key and key in seen:
            row.update(status='duplicate', duplicate_of=seen[key])
        elif key and key in tracked:
            row['status'] = 'tracked'
        elif job['company'].strip().casefold() in excluded:
            row['status'] = 'excluded'
            row['warnings'].append('命中案例中的排除公司名单')
        else:
            deadline = calendar_day(job.get('deadline'))
            posted = calendar_day(job.get('posted_date'))
            row['urgent'] = deadline is not None and 0 <= (deadline - today).days <= 7
            if job.get('deadline') and deadline is None:
                row['warnings'].append('截止日期无法识别，需核实；不会猜测过期')
            if job.get('posted_date') and posted is None:
                row['warnings'].append('发布日期无法识别，需核实')
            if posted and (today - posted).days > 30:
                row['warnings'].append('发布已超过 30 天，请核验仍在招聘')
            if deadline and deadline < today:
                row['status'] = 'expired'
            elif not job.get('jd', '').strip():
                row['status'] = 'missing_jd'
            else:
                items = assess(job['jd'], evidence)
                row['requirements'] = items
                weights = {'required': 3, 'preferred': 1, 'context': 1}
                total = sum(weights[i['level']] for i in items)
                matched = sum(weights[i['level']] for i in items if i['status'] == 'supported')
                row['score'] = round(100 * matched / total) if total else None
                blockers = [i for i in items if i['level'] == 'required' and i['status'] != 'supported']
                row['status'] = ('blocked' if any(i['status'] == 'not_met' for i in blockers) else
                                 'needs_review' if blockers or not items else 'review')
                row['warnings'].append('仅按导入 JD 与本地规则初筛；未联网核验，仍需核对地点、语言与原始证据')
        if key:
            seen.setdefault(key, row['id'])
        results.append(row)
    order = {'review': 0, 'needs_review': 1, 'blocked': 2, 'missing_jd': 3,
             'expired': 4, 'excluded': 5, 'tracked': 6, 'duplicate': 7}
    results.sort(key=lambda r: (order[r['status']], -(r['score'] if r['score'] is not None else -1),
                                not r.get('urgent', False), int(r['id'])))
    return {'as_of': today.isoformat(), 'evidence_sources': evidence['sources'], 'jobs': results, 'gaps': shared_gaps(results),
            'score_label': '证据覆盖初筛分（必需项权重 3，其余 1），不是 ATS 分或录取概率'}


def shared_gaps(rows):
    grouped = {}
    for row in rows:
        if row['status'] not in {'review', 'needs_review', 'blocked'}:
            continue
        for item in row['requirements']:
            if item['status'] == 'supported':
                continue
            text = item['text']
            # Group only a few explicit skill names; preserve original clauses.
            term = re.search(r'(?<![a-zA-Z])(?:SQL|ERP|Python|Excel|RAG|OCR)(?![a-zA-Z])', text, re.I)
            key = term.group().upper() if term else re.sub(r'^[\d\s、.（）()]+', '', text).casefold()
            group = grouped.setdefault(key, {'topic': term.group().upper() if term else text,
                                             'jobs': set(), 'required_jobs': set(), 'examples': []})
            group['jobs'].add(row['id'])
            if item['level'] == 'required':
                group['required_jobs'].add(row['id'])
            group['examples'].append({'job_id': row['id'], 'requirement': text, 'status': item['status']})
    gaps = []
    for group in grouped.values():
        hard = any(re.search(r'学历|本科|硕士|博士|\d+\s*年|工作许可|签证|出差|地点|years?|degree|visa|relocat', e['requirement'], re.I) for e in group['examples'])
        group.update(job_count=len(group['jobs']), required_count=len(group['required_jobs']),
                     priority=len(group['jobs']) + 2 * len(group['required_jobs']),
                     kind='eligibility' if hard else 'evidence_or_skill',
                     next_action=('先核实资格、意愿或经历；短期练习不能替代学历、年限或许可。' if hard else
                                  '先查找已有真实证据；确实缺能力时，用合成或公开数据做一个小练习，保存方法、结果与限制。'),
                     deliverable='资格核对记录' if hard else '标为练习的作品 + 可复现步骤 + 自评记录')
        group['jobs'] = sorted(group['jobs'], key=int)
        group['required_jobs'] = sorted(group['required_jobs'], key=int)
        gaps.append(group)
    return sorted(gaps, key=lambda g: (-g['priority'], g['topic']))


def followups(case, days=10, now=None):
    if type(days) is not int or not 1 <= days <= 365:
        raise ValueError('静默天数应为 1–365 的整数')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('当前时间必须包含时区')
    path = local_file(case, 'application-events.jsonl')
    events = []
    event_ids = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if (not isinstance(event, dict) or not event_time(event.get('timestamp'))
                    or not isinstance(event.get('job_key'), str) or not event['job_key'].strip()
                    or not isinstance(event.get('event_id'), str) or not event['event_id'].strip()):
                raise ValueError('投递事件缺少编号或带时区时间，请先修复后再生成跟进清单')
            if event['event_id'] in event_ids:
                if event_ids[event['event_id']] != event:
                    raise ValueError('同一事件编号的内容冲突，请先修复')
                continue
            event_ids[event['event_id']] = event
            events.append(event)
    due, held = [], []
    for row in tracker(case):
        status = row.get('status') or row.get('application_status')
        if status not in {'submitted', 'assessment', 'interview'}:
            continue
        key = row['job_key']
        log = sorted([e for e in events if e.get('job_key') == key], key=lambda e: event_time(e['timestamp']))
        reason = ''
        submissions = [e for e in log if e.get('action') == 'attempt_result' and e.get('result') == 'submitted']
        if not submissions:
            reason = '缺少确认投递事件；不从台账阶段猜测投递日期'
        elif any(event_time(e['timestamp']) > now for e in log):
            reason = '事件含未来时间，请先核实'
        elif row.get('execution_status') in {'submission_unknown', 'filling', 'blocked'}:
            reason = '执行状态尚未核实'
        elif any(e.get('action') in {'offer', 'rejected', 'withdrawn'} for e in log[log.index(submissions[-1]) + 1:]):
            reason = '已有后续终止或 Offer 事件，请先更新台账'
        if reason:
            held.append({'job_key': key, 'reason': reason})
            continue
        submitted = submissions[-1]
        attempt = submitted.get('attempt_id')
        begin = next((e for e in log if attempt and e.get('attempt_id') == attempt
                      and e.get('action') == 'attempt_started'), None)
        if not begin or event_time(begin['timestamp']) > event_time(submitted['timestamp']):
            held.append({'job_key': key, 'reason': '确认事件缺少有效的申请开始记录，请先修复'})
            continue
        # A delayed confirmation must not reset follow-ups already sent during
        # that attempt. Incomplete legacy logs need evidence repair first.
        subsequent = log[log.index(begin):]
        invalid_evidence = False
        for event in subsequent:
            if event.get('action') == 'attempt_started':
                continue
            try:
                relative = event.get('evidence_path')
                if (event.get('source') not in {'user_report', 'tool_observation'}
                        or not isinstance(relative, str) or not relative
                        or not local_file(case, relative).is_file()):
                    invalid_evidence = True
            except (ValueError, OSError):
                invalid_evidence = True
        if invalid_evidence:
            held.append({'job_key': key, 'reason': '本轮事件缺少有效来源或案例内证据文件，请先核实'})
            continue
        starts = {e.get('attempt_id') for e in subsequent if e.get('action') == 'attempt_started'}
        finals = {e.get('attempt_id') for e in subsequent if e.get('action') == 'attempt_result' and e.get('result') in {'submitted', 'not_submitted'}}
        current = [e for e in subsequent if not attempt or not e.get('attempt_id') or e.get('attempt_id') == attempt]
        if any(e.get('action') in {'offer', 'rejected', 'withdrawn'} for e in current):
            held.append({'job_key': key, 'reason': '本轮已有终止或 Offer 事件，请先更新台账'})
            continue
        if starts - finals or any(e.get('result') not in {'sent', 'draft', 'not_sent', 'failed'} for e in subsequent if e.get('action') == 'followup'):
            held.append({'job_key': key, 'reason': '存在结果未核实的申请或跟进，请先核对外部记录'})
            continue
        sent = [e for e in current if e.get('action') == 'followup' and e.get('result') == 'sent']
        if len(sent) >= 2:
            held.append({'job_key': key, 'reason': '本轮申请已有两次成功跟进记录'})
            continue
        activity = [e for e in current if e.get('action') in {'attempt_result', 'reply', 'assessment', 'interview'} or e in sent]
        last = max(event_time(e['timestamp']) for e in activity)
        quiet_days = (now - last).days
        if quiet_days < days:
            continue
        company, role = row.get('company', ''), row.get('role', '')
        due.append({'job_key': key, 'company': company, 'role': role, 'quiet_days': quiet_days,
                    'followups_sent': len(sent), 'last_activity': last.isoformat(),
                    'source_event_id': submitted.get('event_id'), 'recipient': '', 'draft_only': True,
                    'draft': f'您好，我此前申请了贵司的「{role}」岗位，想了解目前的招聘进展。如需补充材料，烦请告知。感谢您的时间！'})
    due.sort(key=lambda r: (-r['quiet_days'], r['job_key']))
    return {'as_of': now.isoformat(), 'days': days, 'due': due, 'held': held,
            'note': '按最后记录活动计算静默；发送前核对邮箱/平台是否已有回复，草稿不计作发送。'}


def run(case, request):
    result = rank_jobs(case, request)
    identifier = 'strategy-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    folder = local_file(case, 'generated/' + identifier)
    folder.mkdir(parents=True, exist_ok=False)
    for name, value in [('request.json', request), ('strategy.json', result)]:
        local_file(case, f'generated/{identifier}/{name}').write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    result['file'] = f'generated/{identifier}/strategy.json'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--jobs', type=Path, help='包含 jobs 数组的 JSON；不传时列待跟进清单')
    parser.add_argument('--days', type=int, default=10)
    args = parser.parse_args()
    try:
        result = run(args.case, json.loads(args.jobs.read_text(encoding='utf-8'))) if args.jobs else followups(args.case, args.days)
    except (ValueError, OSError, TypeError, KeyError) as error:
        parser.exit(2, str(error) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
