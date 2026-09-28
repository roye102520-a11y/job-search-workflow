"""Local career workspace: source-backed overview, review notes, portfolio drafts."""
import csv
import json
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path

DOCUMENTS = {'career-evidence-bank.md', 'coaching-state.md', 'role-directions.md', 'direction-review.md', 'materials-summary.md', 'company-shortlist.md'}
DIMENSIONS = ['证据', '结构', '岗位相关性', '个人贡献', '可信度']
PREFERENCE_CATEGORIES = ['产品运营', '用户运营', '内容运营', 'AI/知识库运营', '项目管理', '数据分析', '销售支持', '客户成功']
PREFERENCE_LOCATIONS = ['上海', '北京', '杭州', '苏州', '深圳', '南京', '中国香港', '新加坡', '马德里', '远程']
PREFERENCE_REQUESTS = ['互联网大厂', 'AI 产品', '知识库/RAG', '内容与社区', '用户生命周期', '跨团队协同', '接受社招', '英文环境']


def local_file(case, relative):
    base = Path(case).resolve()
    path = base / relative
    if not path.resolve().is_relative_to(base) or any(p.is_symlink() for p in [path, *path.parents] if p != base and p.is_relative_to(base)):
        raise ValueError('文件必须位于当前求职案例内')
    return path


def read_json(case, relative, default):
    path = local_file(case, relative)
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def source_text(case, relative):
    path = local_file(case, relative)
    return path.read_text(encoding='utf-8') if path.is_file() else ''


def preferences(case):
    value = read_json(case, 'search-preferences.json', {})
    if not isinstance(value, dict):
        raise ValueError('岗位偏好格式错误')
    return {**value,
            'categories': [x for x in value.get('categories', []) if x in PREFERENCE_CATEGORIES],
            'locations': [x for x in value.get('locations', value.get('cities', [])) if x in PREFERENCE_LOCATIONS],
            'requests': [x for x in value.get('requests', []) if x in PREFERENCE_REQUESTS]}


def save_preferences(case, request):
    if not isinstance(request, dict) or set(request) - {'categories', 'locations', 'requests'}:
        raise ValueError('岗位偏好字段无效')
    clean = {}
    for key, allowed in [('categories', PREFERENCE_CATEGORIES), ('locations', PREFERENCE_LOCATIONS), ('requests', PREFERENCE_REQUESTS)]:
        values = request.get(key, [])
        if not isinstance(values, list) or any(not isinstance(x, str) or x not in allowed for x in values):
            raise ValueError('岗位偏好选项无效')
        clean[key] = list(dict.fromkeys(values))
    prior = preferences(case)
    clean.update({'preferred_companies': prior.get('preferred_companies', []), 'excluded_companies': prior.get('excluded_companies', []), 'cities': clean['locations'], 'updated_at': datetime.now(timezone.utc).date().isoformat(), 'source': 'user_selected_in_workspace'})
    local_file(case, 'search-preferences.json').write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding='utf-8')
    return clean


def recommendations(case):
    pref = preferences(case)
    entries = read_json(case, 'resume-evidence.json', {}).get('entries', [])
    tags = {tag for entry in entries for bullet in entry.get('bullets', []) for tag in bullet.get('tags', [])}
    catalog = [
        {'id': 'bytedance-ai-learning-ops', 'company': '字节跳动', 'title': 'AI学习能力产品运营-中国广告销售平台', 'locations': ['上海', '北京'], 'categories': ['产品运营', 'AI/知识库运营'], 'requests': ['互联网大厂', 'AI 产品', '跨团队协同'], 'url': 'https://jobs.bytedance.com/experienced/position/7574062969937234181/detail?spread=PJUJ6P6', 'status': '用户提供岗位链接，官网有效性待核验'},
        {'id': 'bytedance-agent-ops', 'company': '字节跳动', 'title': 'AI产品运营（商家Agent方向）-TikTok Shop', 'locations': ['上海'], 'categories': ['产品运营', 'AI/知识库运营'], 'requests': ['互联网大厂', 'AI 产品', '跨团队协同'], 'url': '', 'status': '截图线索，需官网重新核验'},
        {'id': 'bytedance-certification-ops', 'company': '字节跳动', 'title': '巨量认证运营经理-中国广告销售平台（上海）', 'locations': ['上海'], 'categories': ['用户运营', '内容运营', '项目管理'], 'requests': ['互联网大厂', '用户生命周期', '跨团队协同'], 'url': '', 'status': '截图线索，需官网重新核验'},
        {'id': 'netease-content-ops', 'company': '网易', 'title': '内容/用户运营（社会招聘方向）', 'locations': ['杭州', '广州'], 'categories': ['内容运营', '用户运营'], 'requests': ['互联网大厂', '内容与社区', '用户生命周期'], 'url': '', 'status': '公司方向推荐，具体职位待官网核验'},
        {'id': 'xiaohongshu-community-ops', 'company': '小红书', 'title': '社区/内容运营（社会招聘方向）', 'locations': ['上海'], 'categories': ['内容运营', '用户运营'], 'requests': ['互联网大厂', '内容与社区', '用户生命周期'], 'url': '', 'status': '公司方向推荐，需切换社会招聘页核验'},
    ]
    excluded = {str(x).lower() for x in pref.get('excluded_companies', [])}
    result = []
    for job in catalog:
        if job['company'].lower() in excluded:
            continue
        category_hits = len(set(pref['categories']) & set(job['categories']))
        location_hits = len(set(pref['locations']) & set(job['locations']))
        request_hits = len(set(pref['requests']) & set(job['requests']))
        evidence_hits = []
        if 'ai-content-operations' in tags and ('AI/知识库运营' in job['categories'] or 'AI 产品' in job['requests']): evidence_hits.append('有 AI 内容或知识库相关事实条目')
        if 'user-operations' in tags and '用户运营' in job['categories']: evidence_hits.append('有用户或客户运营相关事实条目')
        if 'implementation-support' in tags and '跨团队协同' in job['requests']: evidence_hits.append('有实施支持相关事实条目')
        if 'product-operations' in tags and '产品运营' in job['categories']: evidence_hits.append('有产品运营相关事实条目')
        result.append({**job, 'score': category_hits * 3 + location_hits * 2 + request_hits + len(evidence_hits) * 2, 'evidence': evidence_hits, 'matched_preferences': category_hits + location_hits + request_hits})
    return sorted(result, key=lambda x: (-x['score'], x['company'], x['title']))


def safe_url(value):
    from urllib.parse import urlsplit
    if not isinstance(value, str):
        return ''
    parsed = urlsplit(value)
    return value if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password else ''


def documents(case):
    case = Path(case).resolve()
    files = set(DOCUMENTS)
    for folder, extensions in [('resume-versions', {'.docx', '.pdf', '.md'}), ('interview-reviews', {'.json'})]:
        root = local_file(case, folder)
        if root.is_dir():
            for path in root.iterdir():
                if path.suffix in extensions and path.is_file() and not path.is_symlink():
                    files.add(path.relative_to(case).as_posix())
    return sorted(name for name in files if local_file(case, name).is_file())


def document(case, relative):
    if relative not in documents(case):
        raise ValueError('这份资料未加入工作台资源索引')
    return local_file(case, relative)


def project_links(evidence_text, entry):
    normalize = lambda value: re.sub(r'\s+', '', value).lower()
    name = normalize(entry.get('title_zh', '').split('｜')[0])
    for section in re.split(r'(?m)^### ', evidence_text):
        if name and name in normalize(section.split('\n', 1)[0]):
            links = {}
            for key, pattern in [('website', r'线上地址[：:]\s*(https?://\S+)'), ('github', r'GitHub[：:]\s*(https?://\S+)')]:
                match = re.search(pattern, section)
                links[key] = safe_url(match.group(1)) if match else ''
            return links
    return {'website': '', 'github': ''}


def snapshot(case):
    case = Path(case).resolve()
    evidence = read_json(case, 'resume-evidence.json', {})
    if not isinstance(evidence, dict):
        raise ValueError('证据缓存格式错误')
    text = source_text(case, 'career-evidence-bank.md')
    coaching = source_text(case, 'coaching-state.md')
    entries = evidence.get('entries', [])
    projects = [{**e, **project_links(text, e)} for e in entries if e.get('kind') == 'project']
    tracker = local_file(case, 'application-tracker.csv')
    applications = []
    if tracker.is_file():
        with tracker.open(encoding='utf-8-sig', newline='') as handle:
            applications = list(csv.DictReader(handle))
    keys = [r.get('job_key') for r in applications]
    if len(keys) != len(set(keys)):
        raise ValueError('投递记录存在重复编号，请先修复再展示统计')
    for row in applications:
        row['status'] = row.get('status') or row.get('application_status') or 'discovered'
        row['url'] = safe_url(row.get('url'))
    history, issues, portfolios, materials = [], [], [], []
    inbox = local_file(case, 'material-inbox')
    if inbox.is_dir():
        for path in sorted(inbox.glob('*/intake.json'), reverse=True):
            try:
                materials.append(read_json(case, path.relative_to(case).as_posix(), {}))
            except (ValueError, OSError):
                issues.append('部分导入材料无法读取')
    if evidence:
        try:
            from resume_pipeline import load_evidence
            load_evidence(case)
        except (ValueError, OSError, KeyError, TypeError) as error:
            issues.append('证据缓存需要复核：' + str(error))
    root = local_file(case, 'generated')
    if root.is_dir():
        for folder in sorted(root.glob('portfolio-*'), reverse=True):
            relative = folder.relative_to(case).as_posix()
            if re.fullmatch(r'portfolio-\d{8}T\d{6}-[a-f0-9]{8}', folder.name) and all(local_file(case, relative + '/' + f).is_file() for f in ('portfolio.md', 'website.html')):
                portfolios.append({'id': folder.name, 'markdown': relative + '/portfolio.md', 'preview': '/portfolio-preview/' + folder.name, 'published': False})
        for path in sorted(root.glob('*/result.json'), reverse=True):
            try:
                relative = path.relative_to(case).as_posix()
                result = read_json(case, relative, {})
                request = read_json(case, str(path.parent.relative_to(case) / 'request.json'), {})
                is_test = bool(re.search(r'合成|synthetic|example\.test', ' '.join(str(request.get(k, '')) for k in ('jd', 'company', 'url')), re.I))
                history.append({'id': path.parent.name, 'title': request.get('title', '岗位材料'), 'company': request.get('company', ''),
                                'family': result.get('family'), 'label': result.get('label'), 'synthetic': is_test,
                                'files': {k: v for k, v in result.get('files', {}).items() if isinstance(v, str) and local_file(case, v).is_file()},
                                'blockers': len(result.get('requirement_summary', {}).get('required_blockers', []))})
            except (ValueError, OSError, TypeError, AttributeError):
                issues.append(path.parent.name + '：材料记录无法读取')
    reviews = []
    for name in documents(case):
        if name.startswith('interview-reviews/'):
            try:
                review = read_json(case, name, {})
                if not isinstance(review, dict) or not isinstance(review.get('scores'), dict):
                    raise ValueError('复盘记录格式错误')
                reviews.append(review)
            except (ValueError, OSError):
                issues.append(name + '：复盘无法读取')
    next_steps = []
    section = re.search(r'## Next Training Plan\n(.*?)(?=\n## |\Z)', coaching, re.S)
    if section:
        next_steps = [re.sub(r'^\d+\.\s*', '', line).strip() for line in section.group(1).splitlines() if re.match(r'^\d+\.', line)]
    counts = dict(Counter(r['status'] for r in applications))
    # Snapshot stages are not a conversion funnel or an inferred submission event.
    event_file = local_file(case, 'application-events.jsonl')
    submitted = set()
    if event_file.is_file():
        for line in event_file.read_text(encoding='utf-8').splitlines():
            if line.strip():
                try:
                    event = json.loads(line)
                    if event.get('action') == 'attempt_result' and event.get('result') == 'submitted':
                        submitted.add(event['job_key'])
                except (ValueError, KeyError, AttributeError):
                    issues.append('部分投递事件无法读取，确认投递数量可能不完整')
    return {'name': evidence.get('person', {}).get('name_zh', '我的求职空间'),
            'website': safe_url(evidence.get('person', {}).get('portfolio', '')),
            'preferences': preferences(case), 'preference_options': {'categories': PREFERENCE_CATEGORIES, 'locations': PREFERENCE_LOCATIONS, 'requests': PREFERENCE_REQUESTS}, 'recommendations': recommendations(case),
            'projects': projects, 'entries': entries, 'documents': documents(case), 'applications': applications,
            'history': history, 'reviews': sorted(reviews, key=lambda x: x.get('created_at', ''), reverse=True),
            'portfolios': portfolios,
            'materials': materials,
            'next_steps': next_steps, 'unconfirmed': evidence.get('unconfirmed', []), 'warnings': issues,
            'stats': {'projects': len(projects), 'evidence': sum(len(e.get('bullets', [])) for e in entries),
                      'resume_versions': sum(n.startswith('resume-versions/') for n in documents(case)),
                      'generated': sum(not h['synthetic'] for h in history), 'synthetic': sum(h['synthetic'] for h in history),
                      'submitted': len(submitted), 'reviews': len(reviews), 'stages': counts},
            'source': '当前案例文件 · 刷新时读取', 'updated_at': datetime.now(timezone.utc).isoformat()}


def save_review(case, request):
    allowed = {'company', 'role', 'date', 'kind', 'question', 'answer', 'feedback', 'next_action', 'scores', 'job_key', 'id'}
    if not isinstance(request, dict) or set(request) - allowed:
        raise ValueError('复盘字段无效')
    for key in allowed - {'scores'}:
        if not isinstance(request.get(key, ''), str) or len(request.get(key, '')) > 12000:
            raise ValueError('复盘内容须为文字，每项不超过 12000 字')
    for key in ('date', 'question', 'next_action'):
        if not request.get(key, '').strip():
            raise ValueError('请填写日期、问题和下一步改进')
    from datetime import date
    date.fromisoformat(request['date'])
    if request.get('kind') not in ('practice', 'interview'):
        raise ValueError('请选择模拟练习或真实面试')
    scores = request.get('scores', {})
    if not isinstance(scores, dict) or set(scores) - set(DIMENSIONS) or any(type(v) is not int or not 1 <= v <= 5 for v in scores.values()):
        raise ValueError('评分应为 1–5 的整数；没有评分可留空')
    key = request.get('job_key', '')
    if key and not any(r['job_key'] == key for r in snapshot(case)['applications']):
        raise ValueError('关联岗位不在投递记录中')
    identifier = request.get('id') or str(uuid.uuid4())
    if not re.fullmatch(r'[a-f0-9-]{36}', identifier):
        raise ValueError('复盘 ID 无效')
    folder = local_file(case, 'interview-reviews')
    folder.mkdir(exist_ok=True)
    path = local_file(case, 'interview-reviews/' + identifier + '.json')
    content = {**request, 'id': identifier, 'source': 'user_report', 'created_at': datetime.now(timezone.utc).isoformat()}
    if path.exists():
        prior = json.loads(path.read_text(encoding='utf-8'))
        comparable = lambda x: {k: v for k, v in x.items() if k != 'created_at'}
        if comparable(prior) == comparable(content):
            return prior
        raise ValueError('该复盘已保存，内容变更请创建新记录')
    # Exclusive creation avoids overwriting an earlier review; server serializes writes.
    with path.open('x', encoding='utf-8') as handle:
        json.dump(content, handle, ensure_ascii=False, indent=2)
    return content


def build_portfolio(case, request):
    from resume_pipeline import load_evidence
    data = load_evidence(Path(case).resolve())
    if not isinstance(request, dict) or set(request) - {'project_ids', 'resume_id'}:
        raise ValueError('作品集字段无效')
    resume_id = request.get('resume_id', '')
    label = '职业经历与项目实践'
    if resume_id:
        if not isinstance(resume_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', resume_id):
            raise ValueError('简历版本无效')
        selection = read_json(case, 'generated/' + resume_id + '/selection.json', {})
        if selection.get('source_digests') != data['sources']:
            raise ValueError('简历版本事实源已过期或版本不存在，请先重新生成')
        from resume_pipeline import FAMILIES
        label = FAMILIES.get(selection.get('family'), label)
        chosen = set(selection.get('selected_bullet_ids', []))
        data['entries'] = [{**e, 'bullets': [b for b in e['bullets'] if b['id'] in chosen]} for e in data['entries']]
    ids = request.get('project_ids') if isinstance(request, dict) else None
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('请至少选择一个项目，且不得重复')
    projects = [e for e in data['entries'] if e['kind'] == 'project' and e['id'] in ids and e['bullets']]
    if len(projects) != len(ids):
        raise ValueError('项目不在当前事实库中')
    if any(isinstance(item, dict) and item.get('field') == 'projects.start_date_conflict' for item in data.get('unconfirmed', [])):
        projects = [{**project, 'dates': '开始日期待本人确认'} for project in projects]
    draft_id = 'portfolio-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    folder = local_file(case, 'generated/' + draft_id)
    folder.mkdir(parents=True)
    markdown = ['# 作品集内容审阅稿', '', '来源：当前已校验证据缓存。尚未发布；数字、译名与个人贡献仍需最终复核。',
                '建议叙事：用户问题 → 本人职责 → 关键取舍 → 交付与证据 → 验证与反思。', '']
    for project in projects:
        markdown += ['## ' + project['title_zh'], '', project['employment_zh'], '']
        markdown += ['- ' + bullet['zh'] for bullet in project['bullets']]
        markdown += ['', '来源：' + project['source_ref'], '', '待补充：目标用户、关键决策依据、可展示截图或 PRD、真实反馈、个人贡献边界。', '']
    (folder / 'portfolio.md').write_text('\n'.join(markdown), encoding='utf-8')
    from portfolio_renderer import render
    (folder / 'website.html').write_text(render(data, projects, label), encoding='utf-8')
    (folder / 'provenance.json').write_text(json.dumps({'source_digests': data['sources'], 'resume_id': resume_id, 'project_ids': ids, 'template': 'portfolio-editorial', 'published': False}, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'id': draft_id, 'markdown': 'generated/' + draft_id + '/portfolio.md', 'preview': '/portfolio-preview/' + draft_id, 'published': False}
