"""Bounded daily discovery and local material preparation.

Discovery only reads reviewed public ATS feeds and stores jobs in the existing
Manifest/Tracker. Preparation reuses resume_pipeline. This module never sends
email, fills forms, starts an application attempt, or submits an application.
It does not install or schedule itself; a local scheduler must invoke it.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import career_positioning
import foreign_opportunities
import job_data
from career_workspace import local_file
from resume_pipeline import generate, load_evidence


MAX_DAILY_RESULTS = 100
MAX_PER_TENANT = 10
MAX_PREPARATION_RESULTS = 10
DEFAULT_TENANTS = ('veeva', 'getwingapp', 'weloglobal', 'rws')
TERMINAL_STAGES = {'submitted', 'assessment', 'interview', 'offer', 'rejected', 'withdrawn', 'closed'}


def discover_daily(case, limit=10, tenants=None, transport=None):
    if type(limit) is not int or not 1 <= limit <= MAX_DAILY_RESULTS:
        raise ValueError('每日扫描上限为 1–100 条线索；每个已审核来源最多 10 个，实际数量取决于接入来源和在招岗位')
    selected = list(tenants or DEFAULT_TENANTS)
    if (not selected or len(selected) != len(set(selected))
            or any(tenant not in foreign_opportunities.LEVER for tenant in selected)):
        raise ValueError('只能选择已经审核支持的官方 Lever 租户')
    remaining = limit
    results, sources = [], []
    for index, tenant in enumerate(selected):
        quota = min(MAX_PER_TENANT, (remaining + len(selected) - index - 1) // (len(selected) - index))
        if quota <= 0: break
        try:
            response = foreign_opportunities.discover(case, tenant, quota, transport)
            imported = response.get('results', []) if isinstance(response, dict) else []
            results.extend((tenant, row) for row in imported[:quota])
            sources.append({'tenant': tenant, 'status': 'read', 'returned': min(len(imported), quota)})
        except (OSError, ValueError, TypeError, KeyError) as error:
            sources.append({'tenant': tenant, 'status': 'unavailable', 'reason': str(error)[:240]})
        remaining = limit - len(results)
    saved = {row['job_key']: row for row in foreign_opportunities.list_jobs(case).get('jobs', [])}
    rows = []
    for tenant, imported in results:
        key = imported.get('job_key')
        job = saved.get(key) or imported.get('job') or {}
        match = job.get('match') if isinstance(job.get('match'), dict) else {}
        verification = job.get('verification') if isinstance(job.get('verification'), dict) else {}
        rows.append({
            'job_key': key, 'tenant': tenant, 'company': job.get('company', foreign_opportunities.LEVER[tenant]),
            'title': job.get('title', '岗位待核实'), 'url': job.get('url', ''),
            'location': job.get('location', '未知'), 'tracker_status': imported.get('status', 'discovered'),
            'duplicate': bool(imported.get('duplicate')),
            'verification_status': verification.get('status', 'unknown'),
            'verified_at': verification.get('verified_at'),
            'grade': match.get('grade', 'U'),
            'grade_reasons': match.get('grade_reasons', []),
            'employment_category': match.get('employment_category', 'unknown'),
            'internship_qualification': match.get('internship_qualification'),
            'posted_compensation': match.get('posted_compensation'),
            'global_work_eligibility': match.get('global_work_eligibility', {'status': 'not_applicable'}),
            'work_mode': match.get('work_mode'),
            'external_action': 'none',
        })
    return {
        'run_at': datetime.now(timezone.utc).isoformat(), 'mode': 'discovery-only',
        'max_results': limit, 'results_count': len(rows), 'sources': sources, 'jobs': rows,
        'external_actions': {'emails_sent': 0, 'applications_submitted': 0},
        'scheduler': 'not_configured',
        'coverage_note': '仅检索已审核接入的官方 Lever 租户；本配置当前最多 4 个来源 × 10 条。未返回岗位不代表其他企业没有职位，不能满足 50–100 条全球线索目标。',
    }


def daily_prepare(case, limit=10, tenants=None, transport=None, font=None):
    """Discover and prepare only safely reviewable jobs; never submits externally."""
    discovery = discover_daily(case, limit, tenants, transport)
    prepared, held = [], []
    seen = set()
    preparation_attempts = 0
    for row in discovery['jobs']:
        key = row.get('job_key')
        if not isinstance(key, str) or key in seen:
            continue
        seen.add(key)
        reasons = []
        if row.get('verification_status') != 'verified_open':
            reasons.append('官网当前开放状态未核验')
        if row.get('grade') != 'A':
            reasons.append('自动准备只处理 A 级；B/C/D/U 仍需人工核实')
        if row.get('employment_category') == 'internship':
            qualification = row.get('internship_qualification') or {}
            if qualification.get('status') != 'eligible':
                reasons.append('已毕业人员资格未由官方确认')
        compensation = row.get('posted_compensation') or {}
        if compensation.get('paid_status') == 'unpaid':
            reasons.append('官方明确为无薪')
        work_eligibility = row.get('global_work_eligibility') or {}
        if work_eligibility.get('status') == 'unknown':
            reasons.append('目标工作地的许可/合法雇佣、签证或远程雇佣资格尚待核实')
        if row.get('duplicate') and row.get('tracker_status') in TERMINAL_STAGES:
            reasons.append('已有结束或提交状态，避免重复准备')
        if reasons:
            held.append({'job_key': key, 'company': row.get('company', ''), 'title': row.get('title', ''),
                         'reasons': reasons})
            continue
        if preparation_attempts >= MAX_PREPARATION_RESULTS:
            held.append({'job_key': key, 'company': row.get('company', ''), 'title': row.get('title', ''),
                         'reasons': ['每日本地材料准备上限为 10 个岗位']})
            continue
        preparation_attempts += 1
        try:
            result = prepare_selected(case, [key], font=font)
            outputs = result.get('jobs', [])
            successful = []
            for output in outputs:
                languages = {item.get('language') for item in output.get('materials', []) if isinstance(item, dict)}
                if {'en', 'zh'}.issubset(languages):
                    successful.append(output)
                else:
                    errors = [item.get('reason', '') for item in output.get('errors', []) if isinstance(item, dict)]
                    held.append({'job_key': key, 'company': row.get('company', ''), 'title': row.get('title', ''),
                                 'reasons': ['中英文材料未同时生成' + (('：' + '；'.join(errors)) if errors else '')]})
            prepared.extend(successful)
        except (ValueError, OSError, ImportError) as error:
            held.append({'job_key': key, 'company': row.get('company', ''), 'title': row.get('title', ''),
                         'reasons': [str(error)[:240]]})
    return {'run_at': discovery['run_at'], 'mode': 'daily-discovery-and-local-preparation-only',
            'discovery': discovery, 'prepared': prepared, 'held': held,
            'summary': {'discovered': discovery['results_count'], 'prepared': len(prepared), 'held': len(held),
                        'emails_sent': 0, 'applications_submitted': 0},
            'scheduler': 'not_configured',
            'coverage_note': discovery['coverage_note']}


def _load_selected_jobs(case, job_keys):
    if (not isinstance(job_keys, list) or not 1 <= len(job_keys) <= MAX_PREPARATION_RESULTS
            or len(job_keys) != len(set(job_keys))
            or any(not isinstance(key, str) or not re.fullmatch(r'opportunity-[a-f0-9]{20}', key) for key in job_keys)):
        raise ValueError('请提供 1–10 个唯一的已发现岗位编号')
    jobs = {row['job_key']: row for row in foreign_opportunities.list_jobs(case).get('jobs', [])}
    selected = []
    for key in job_keys:
        job = jobs.get(key)
        if not job:
            raise ValueError('岗位不存在或未保存：' + key)
        match = job.get('match', {})
        if job.get('verification', {}).get('status') != 'verified_open':
            raise ValueError('官方岗位当前未核验为可申请：' + key)
        if match.get('grade') not in {'A', 'B'}:
            raise ValueError('岗位级别为 C/D/U，暂不生成申请材料：' + key)
        if match.get('employment_category') == 'internship':
            qualification = match.get('internship_qualification', {}).get('status')
            if qualification != 'eligible':
                raise ValueError('实习岗位毕业资格未被官方确认，不能按符合条件生成材料：' + key)
        work_eligibility = match.get('global_work_eligibility')
        if isinstance(work_eligibility, dict) and work_eligibility.get('status') == 'unknown':
            raise ValueError('目标工作地的工作许可、签证或远程雇佣资格尚未确认：' + key)
        if match.get('posted_compensation', {}).get('paid_status') == 'unpaid':
            raise ValueError('无薪岗位默认降级，暂不进入批量材料准备：' + key)
        manifest_path, manifest = next(((path, manifest) for path, manifest in job_data.manifests(Path(case))
                                        if manifest.get('job_key') == key), (None, None))
        if not manifest_path or not manifest:
            raise ValueError('缺少既有岗位 Manifest：' + key)
        if manifest.get('status') in TERMINAL_STAGES or manifest.get('submitted_at'):
            raise ValueError('岗位已有投递或结束记录，不会自动重开申请：' + key)
        if len(job.get('jd', '').strip()) < 40:
            raise ValueError('岗位 JD 不完整：' + key)
        selected.append((job, manifest_path, manifest))
    return selected


def prepare_selected(case, job_keys, font=None):
    case = Path(case).resolve()
    selected = _load_selected_jobs(case, job_keys)
    evidence = load_evidence(case)
    prepared = []
    for job, manifest_path, initial_manifest in selected:
        generated = []
        errors = []
        for language in ('en', 'zh'):
            request = {'jd': job['jd'], 'title': job['title'], 'company': job['company'],
                       'url': job['url'], 'language': language, 'family': 'auto'}
            try:
                result = generate(case, request, font=font)
                generated.append({'language': language, 'output_dir': result['output_dir'],
                                  'files': result.get('files', {}), 'family': result.get('family'),
                                  'status': result.get('status', 'preparing'), 'reused': result.get('reused', False),
                                  'rules_version': result.get('rules_version')})
            except (ValueError, OSError, ImportError) as error:
                errors.append({'language': language, 'reason': str(error)[:240]})

        pdf_versions = [item for item in generated if item['files'].get('pdf')]
        if generated:
            with job_data.lock(case):
                manifest = job_data.read_json(manifest_path)
                if manifest.get('status') in TERMINAL_STAGES or manifest.get('submitted_at'):
                    raise ValueError('准备期间岗位状态已变化；材料已保存在独立版本，但没有修改投递记录：' + job['job_key'])
                versions = manifest.get('prepared_materials', [])
                if not isinstance(versions, list): versions = []
                known = {(entry.get('language'), entry.get('output_dir')) for entry in versions if isinstance(entry, dict)}
                for item in generated:
                    signature = (item['language'], item['output_dir'])
                    if signature not in known:
                        versions.append({**item, 'prepared_at': datetime.now(timezone.utc).isoformat()})
                        known.add(signature)
                manifest['prepared_materials'] = versions[-20:]
                if pdf_versions:
                    chosen = next((item for item in pdf_versions if item['language'] == 'en'), pdf_versions[0])
                    manifest['status'] = 'preparing'
                    manifest['role_family'] = chosen['family']
                    manifest['resume_variant'] = chosen['family'] + '-' + Path(chosen['output_dir']).name
                    manifest['resume_path'] = chosen['files']['pdf']
                    manifest['email_path'] = chosen['files'].get('email', '')
                    manifest['evidence_refs'] = [source['path'] for source in evidence['sources']]
                    resume_path = local_file(case, manifest['resume_path'])
                    manifest['artifacts'] = [{'path': manifest['resume_path'], 'sha256': job_data.digest(resume_path)}]
                    requirements = job.get('match', {}).get('requirements', [])
                    manifest['unresolved_required_fields'] = [item['text'] for item in requirements
                        if item.get('level') == 'required' and item.get('status') != 'supported']
                    manifest['next_action'] = '审核中英文简历、资格和薪资；未发送、未提交。'
                    job_data.validate(case, manifest)
                job_data.atomic(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
                if pdf_versions:
                    job_data.upsert(case, manifest)
        prepared.append({'job_key': job['job_key'], 'company': job['company'], 'title': job['title'],
                         'tracker_status': 'preparing' if pdf_versions else initial_manifest.get('status'),
                         'materials': generated, 'errors': errors, 'external_actions': []})
    return {'mode': 'local-material-preparation-only', 'jobs': prepared,
            'external_actions': {'emails_sent': 0, 'applications_submitted': 0}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--discover', action='store_true', help='按案例偏好扫描已支持的官方 ATS，最多 10 个岗位')
    group.add_argument('--daily-prepare', action='store_true', help='扫描官方来源并为符合条件的岗位生成本地审阅材料；不发送或提交')
    group.add_argument('--prepare-job-key', action='append', help='只为已核验且 A/B 级的岗位生成中英审阅材料；可重复指定，最多 10 个')
    group.add_argument('--positioning', action='store_true', help='输出本地证据职业定位报告')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--tenant', action='append', help='可重复指定已支持的 Lever 租户')
    args = parser.parse_args()
    if args.positioning:
        result = career_positioning.build_report(args.case)
        print(career_positioning.render_markdown(result))
    elif args.discover:
        print(json.dumps(discover_daily(args.case, args.limit, args.tenant), ensure_ascii=False, indent=2))
    elif args.daily_prepare:
        print(json.dumps(daily_prepare(args.case, args.limit, args.tenant), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(prepare_selected(args.case, args.prepare_job_key), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
