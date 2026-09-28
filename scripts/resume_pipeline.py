#!/usr/bin/env python3
"""Offline JD-to-review-package engine. Selects sourced wording, never invents facts.

The Codex skill and local Studio share generate(). No network, shell, AI key, or
application submission. Semantic review remains a separate agent/human step.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit
from xml.sax.saxutils import escape
from jd_requirements import assess as assess_requirements, summary as requirement_summary

FAMILIES = {
    'user-operations': '用户 / 客户运营',
    'ai-content-operations': 'AI 知识库 / 内容运营',
    'implementation-support': '项目交付 / 实施支持',
    'product-operations': '产品助理 / 产品运营',
}
TERMS = {
    'user-operations': ['用户运营', '客户运营', '客户成功', '用户服务', '客户服务', '学员', '用户分层', 'customer success', 'customer operations', 'customer support', 'customer service', 'onboarding'],
    'ai-content-operations': ['知识库', '内容运营', '文档清洗', '结构化', '问答', '质量检查', '离线评测', 'knowledge base', 'content operations', 'data annotation', 'ocr'],
    'implementation-support': ['实施', '项目助理', '项目交付', '项目经理', '验收', '进度', '操作指南', 'implementation', 'project assistant', 'delivery support', 'project coordinator'],
    'product-operations': ['产品助理', '产品运营', '产品经理', '用户路径', '信息分类', '竞品', '需求文档', 'product assistant', 'product operations', 'product manager', 'prd'],
}

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def local(case, value):
    require(isinstance(value, str) and value, '证据文件路径无效')
    path = (case / value.split('#')[0]).resolve()
    require(path.is_relative_to(case.resolve()) and path.is_file(), '证据必须是案例内现存文件：' + value)
    return path

def canonical_job_url(value):
    """Local comparison only; keep meaningful query terms such as requisition IDs."""
    parts = urlsplit(value.strip())
    ignored = {'gclid', 'fbclid', 'trid'}
    query = urlencode(sorted(
        (key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith('utm_') and key.lower() not in ignored
    ))
    return (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), query)


def _labeled_value(jd, labels):
    """Read a short title/company value only when the JD labels it explicitly."""
    for label in labels:
        match = re.search(r'(?:^|\n|[。；;】])\s*' + label + r'\s*[:：]\s*([^\n]+)', jd, re.I)
        if not match:
            continue
        value = re.split(r'[，,。；;|｜]', match.group(1), maxsplit=1)[0].strip()
        if 2 <= len(value) <= 256:
            return value
    return ''


def resolve_metadata(request):
    """Allow a pasted JD to stand alone while preserving missing-field warnings."""
    require(isinstance(request.get('jd'), str) and request['jd'].strip(), '请填写 jd')
    effective = dict(request)
    resolution, warnings = {}, []
    fields = (
        ('title', ('岗位名称', '职位名称', 'job title', 'position', '岗位', '职位'), '岗位名称待确认', '岗位名称'),
        ('company', ('公司名称', 'employer', 'company', '公司', '雇主'), '公司待确认', '公司名称'),
    )
    for field, labels, placeholder, display in fields:
        supplied = request.get(field, '')
        require(isinstance(supplied, str), field + ' 必须是文字')
        supplied = supplied.strip()
        if supplied:
            value, source = supplied, 'input'
        else:
            inferred = _labeled_value(request['jd'], labels)
            if inferred:
                value, source = inferred, 'jd_label'
                warnings.append('已从 JD 的明确标签提取' + display + '：“' + value + '”；请在外发前复核。')
            else:
                value, source = placeholder, 'placeholder'
                warnings.append('未填写' + display + '；本地材料暂标记为“' + placeholder + '”，外发前必须补全。')
        effective[field] = value
        resolution[field] = {'value': value, 'source': source}
    return effective, resolution, warnings

def existing_package_for_url(case, url):
    """Return an existing application manifest with the same normalized URL."""
    target = canonical_job_url(url)
    for manifest_path in sorted((case / 'applications').glob('*/manifest.json')):
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        urls = [manifest.get('url', '')] + list(manifest.get('aliases', []) or [])
        for candidate in urls:
            if isinstance(candidate, str) and candidate.strip() and canonical_job_url(candidate) == target:
                return manifest_path
    return None

def positive_clauses(text):
    # Conservative sentence-level exclusion, not a general language parser.
    return [s.strip() for s in re.split(r'[。；;\n]', text) if s.strip() and not re.search(
        r'不要求|没有.*要求|不是|未将|not required|does not require|no .*required', s, re.I)]

def route(jd, title='', requested='auto'):
    require(requested in ('auto', *FAMILIES), '不支持的方向；请选择自动或已支持方向')
    body = ' '.join(positive_clauses(jd)).lower()
    unsupported = re.search(r'机器学习.*工程师|算法.*工程师|研究工程师|software engineer|machine learning|research scientist', title, re.I)
    unsupported = unsupported or re.search(r'分布式模型训练|pytorch.*训练框架', body, re.I)
    scores = {f: sum(4 for t in terms if t in title.lower()) + sum(1 for t in terms if t in body)
              for f, terms in TERMS.items()}
    if unsupported:
        return {'family': None, 'label': '现有模板不支持此技术方向', 'outcome': 'unsupported', 'scores': scores,
                'warnings': ['本模板覆盖运营、内容、实施支持和产品助理；不能把 AI 应用实践包装为研究或工程资历。请由 Codex 单独评估硬门槛。']}
    if re.search(r'\bae\b|account executive|客户执行', title, re.I):
        return {'family': None, 'label': '客户执行职责需确认', 'outcome': 'ambiguous', 'scores': scores,
                'warnings': ['AE 已按客户执行理解；仍需确认行业、客户类型、拓客签单及回款责任，不自动套用销售简历。']}
    ranking = sorted(scores, key=scores.get, reverse=True)
    if requested == 'auto' and (scores[ranking[0]] < 2 or scores[ranking[0]] == scores[ranking[1]]):
        return {'family': None, 'label': '方向待确认', 'outcome': 'ambiguous', 'scores': scores,
                'warnings': ['JD 信息不足或多个方向相近；补充完整职责，或明确选择方向后生成审阅稿。']}
    family = requested if requested != 'auto' else ranking[0]
    return {'family': family, 'label': FAMILIES[family], 'outcome': 'draft', 'scores': scores,
            'warnings': [] if requested == 'auto' else ['采用用户指定方向；这不表示岗位硬门槛已经满足。']}

def load_evidence(case):
    path = local(case, 'resume-evidence.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(data, dict) and data.get('schema_version') == 1, '证据缓存 schema_version 应为 1')
    require(isinstance(data.get('sources'), list) and data['sources'], '缓存缺少事实源摘要')
    for source in data['sources']:
        require(isinstance(source, dict) and sha(local(case, source.get('path'))) == source.get('sha256'),
                '事实源已变化，请先让 Codex 重新核对证据缓存；不会使用过期表述')
    require(isinstance(data.get('person'), dict), '缺少 person 信息')
    for key in ('name_zh', 'name_en', 'education_zh', 'education_en'):
        require(isinstance(data['person'].get(key), str) and data['person'][key].strip(), '缺少基础字段 ' + key)
    require(isinstance(data.get('entries'), list) and data['entries'], '缺少经历条目')
    ids = set()
    for entry in data['entries']:
        require(isinstance(entry, dict) and entry.get('kind') in ('work', 'project'), '经历类型错误')
        require(isinstance(entry.get('id'), str) and entry['id'] not in ids, '经历 ID 缺失或重复')
        ids.add(entry['id'])
        local(case, entry.get('source_ref'))
        for field in ('title_zh', 'title_en', 'dates', 'employment_zh', 'employment_en'):
            require(isinstance(entry.get(field), str) and entry[field].strip(), '经历缺少 ' + field)
        require(isinstance(entry.get('bullets'), list) and entry['bullets'], '经历没有内容')
        for bullet in entry['bullets']:
            require(isinstance(bullet, dict) and isinstance(bullet.get('id'), str) and bullet['id'] not in ids, '要点 ID 缺失或重复')
            ids.add(bullet['id'])
            for lang in ('zh', 'en'):
                require(isinstance(bullet.get(lang), str) and bullet[lang].strip(), '要点缺少中英文本')
                require(not re.search(r'needs confirmation|待确认|\[TODO\]|\{\{', bullet[lang], re.I), '简历要点含占位内容')
                compact = re.sub(r'\s+', '', bullet[lang]).lower()
                for denied in data.get('excluded_claims', []):
                    require(re.sub(r'\s+', '', denied).lower() not in compact, '要点包含已否定的主张')
            for field in ('tags', 'keywords'):
                require(isinstance(bullet.get(field), list) and all(isinstance(v, str) for v in bullet[field]), '要点标签格式错误')
    return data

def select(data, family, jd):
    body = ' '.join(positive_clauses(jd)).lower()
    def score(entry, bullet):
        return (3 if family in bullet['tags'] else 0) + sum(2 for k in bullet['keywords'] if k.lower() in body) + (1 if family in entry.get('tags', []) else 0) + entry.get('family_priorities', {}).get(family, 0) + (2 if bullet.get('anchor') else 0)
    scored = []
    for entry in data['entries']:
        bullets = sorted(entry['bullets'], key=lambda b: (-score(entry, b), b['id']))
        scored.append({**entry, 'bullets': bullets, 'score': max(score(entry, b) for b in bullets)})
    works = sorted([e for e in scored if e['kind'] == 'work'], key=lambda e: e['dates'], reverse=True)
    projects = sorted([e for e in scored if e['kind'] == 'project'], key=lambda e: (-e['score'], e['id']))
    # Keep a chronological employment record; vary emphasis and project allocation.
    for entry in works:
        anchors = [b for b in entry['bullets'] if b.get('anchor')]
        rest = [b for b in entry['bullets'] if not b.get('anchor')]
        # A neutral adjacent role can still provide a truthful supporting detail.
        # Preserve two sourced bullets unless the role is explicitly a negative
        # match for this family; this prevents a sparse one-page chronology.
        entry['bullets'] = (anchors + rest)[:2 if entry['score'] >= 0 else 1]
    projects = projects[:1 if family in ('user-operations', 'implementation-support') else 2]
    for entry in projects:
        entry['bullets'] = entry['bullets'][:2]
    selected = works + projects
    # A top highlight must not consume every bullet from the same job. Keeping
    # the strongest candidate per entry leaves each chronological role with its
    # own supporting detail below and avoids a résumé that only changes headings.
    strongest = sorted([(entry, entry['bullets'][0]) for entry in selected if entry['bullets']],
                       key=lambda pair: (-score(*pair), pair[1]['id']))[:2]
    return selected, strongest[:2]

def text_lines(person, entries, strongest, title, lang, family):
    labels = {'zh': ('匹配亮点', '工作经历', '相关个人项目', '教育与语言'),
              'en': ('RELEVANT EVIDENCE', 'EXPERIENCE', 'SELECTED PERSONAL PROJECTS', 'EDUCATION & LANGUAGES')}[lang]
    lines = [('name', person['name_' + lang]), ('headline', title)]
    contacts = [person.get('location_' + lang, ''), person.get('phone', ''), person.get('email', '')]
    lines.append(('contact', ' | '.join(x for x in contacts if x)))
    if person.get('portfolio'):
        lines.append(('contact', person['portfolio']))
    lines.append(('section', labels[0]))
    highlight_ids = {bullet['id'] for _, bullet in strongest}
    for entry, bullet in strongest:
        # Label the source at the top and avoid printing the same bullet again below.
        source = entry['title_' + lang].split('|')[0]
        lines.append(('bullet', source + '：' + bullet[lang] if lang == 'zh' else source + ': ' + bullet[lang]))
    kinds = ['project', 'work'] if family in ('product-operations', 'ai-content-operations') else ['work', 'project']
    for kind in kinds:
        group = [e for e in entries if e['kind'] == kind]
        if group:
            lines.append(('section', labels[1 if kind == 'work' else 2]))
        for entry in group:
            dates = entry['dates'].replace('至今', 'Present') if lang == 'en' else entry['dates']
            lines.append(('job', entry['title_' + lang] + ' | ' + entry['employment_' + lang] + ' | ' + dates))
            body_bullets = [b for b in entry['bullets'] if b['id'] not in highlight_ids]
            lines.extend(('bullet', b[lang]) for b in body_bullets)
    lines += [('section', labels[3]), ('body', person['education_' + lang]), ('body', person.get('languages_' + lang, ''))]
    return lines

def render_pdf(path, lines, font=None):
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import SimpleDocTemplate, Paragraph, HRFlowable
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError('需要 Python 依赖 reportlab 与 pypdf；请使用项目 requirements.txt') from exc
    candidates = [font, os.environ.get('RESUME_FONT_PATH'), '/System/Library/Fonts/Supplemental/Arial Unicode.ttf', '/usr/share/fonts/truetype/arphic/uming.ttc']
    font_path = next((Path(x) for x in candidates if x and Path(x).is_file()), None)
    require(font_path is not None, '需要可嵌入的中文 TrueType 字体；设置 RESUME_FONT_PATH 或 --font')
    font_name = 'Resume-' + sha(font_path)[:12]
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    base = dict(fontName=font_name, fontSize=10, leading=14.5, textColor=HexColor('#253643'), wordWrap='CJK', spaceAfter=4)
    sizes = {'name': (23, 29), 'headline': (12, 18), 'contact': (9, 13), 'section': (11, 17), 'job': (10.1, 15), 'body': (10, 14.5), 'bullet': (10, 14.5)}
    story, height = [], 0
    for kind, value in lines:
        style_args = dict(base, fontSize=sizes[kind][0], leading=sizes[kind][1])
        if kind == 'section':
            style_args.update(spaceBefore=9, spaceAfter=5, textColor=HexColor('#11686a'))
        if kind == 'bullet':
            style_args.update(leftIndent=9, firstLineIndent=-9)
        style = ParagraphStyle(kind, **style_args)
        text = escape(value.replace('–', '-').replace('—', '-'))
        if kind == 'bullet':
            text = '- ' + text
        if kind == 'contact' and value.startswith('https://'):
            text = '<link href="' + escape(value, {'"': '&quot;'}) + '">' + text + '</link>'
        para = Paragraph(text, style)
        height += para.wrap(A4[0] - 88, A4[1])[1] + style.spaceBefore + style.spaceAfter
        story.append(para)
    require(height < A4[1] - 86, '内容超过一页容量；请缩减要点，保持 10pt 正文字号，不能裁切或自动缩小字体')
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=38, rightMargin=38, topMargin=30, bottomMargin=30,
                      title=lines[1][1], author=lines[0][1]).build(story)
    reader = PdfReader(path)
    require(len(reader.pages) == 1, 'PDF 不是一页，停止交付')
    extracted = reader.pages[0].extract_text() or ''
    compact = lambda x: re.sub(r'\s+', '', x.replace('–', '-').replace('—', '-'))
    require(all(compact(t) in compact(extracted) for _, t in lines if t.strip()), 'PDF 文本提取不完整，停止交付')
    return {'pages': 1, 'text_extractable': True, 'font_size_pt': 10, 'visual_review': 'pending'}

def write(path, value):
    path.write_text(value, encoding='utf-8')

def json_write(path, value):
    write(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def generate(case, request, font=None):
    case = Path(case).resolve()
    require(case.is_dir(), '案例目录不存在')
    require(isinstance(request, dict), '请求必须为 JSON 对象')
    request, metadata_resolution, metadata_warnings = resolve_metadata(request)
    require(40 <= len(request['jd']) <= 30000, '请提供 40–30000 字符的 JD 正文，链接不能替代正文')
    require(len(request['title']) <= 256 and len(request['company']) <= 256, '公司或岗位名过长')
    lang = request.get('language', 'zh')
    require(lang in ('zh', 'en'), '材料语言应为 zh 或 en')
    url = request.get('url', '')
    require(isinstance(url, str), '岗位链接应为文本')
    if url:
        parts = urlsplit(url)
        require(parts.scheme in ('https', 'http') and parts.hostname and not parts.username and not parts.password, '岗位链接格式错误')
    existing_package = existing_package_for_url(case, url) if url else None
    data = load_evidence(case)
    routing = route(request['jd'], request['title'], request.get('family', 'auto'))
    family = routing['family']
    requirements = assess_requirements(request['jd'], data)
    requirements_summary = requirement_summary(requirements)
    generated = (case / 'generated').resolve()
    require(generated.is_relative_to(case), 'generated 目录不能指向案例外')
    generated.mkdir(exist_ok=True)
    # Never overwrite an earlier JD/version or a submitted attachment.
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:10]
    target = generated / run
    stage = Path(tempfile.mkdtemp(prefix='.building-', dir=generated))
    result = {'family': family, 'label': routing['label'], 'outcome': routing['outcome'], 'warnings': list(routing['warnings']),
              'output_dir': target.relative_to(case).as_posix(), 'files': {}, 'selected_bullet_ids': [], 'status': 'preparing',
              'requirements': requirements, 'requirement_summary': requirements_summary,
              'metadata_resolution': metadata_resolution}
    result['warnings'].extend(metadata_warnings)
    if existing_package:
        result['warnings'].append('该官网链接已有岗位包：' + existing_package.relative_to(case).as_posix() + '。本次只生成新的审阅材料，不建立第二个投递清单。')
    try:
        json_write(stage / 'request.json', request)
        write(stage / 'jd.md', '# ' + request['company'] + ' | ' + request['title'] + '\n\n来源：' + (url or '用户粘贴；无可核验链接') + '\n\n' + request['jd'] + '\n')
        if requirements_summary['required_blockers']:
            result['warnings'].append('存在未满足或尚未核实的必需项；本次只能保留审阅稿，不能标记为投递就绪。')
        if not family:
            requirement_lines = ['# ' + routing['label'], '', '## 硬门槛检查', '', '| 要求 | 层级 | 判断 | 依据与边界 |', '|---|---|---|---|']
            status_labels = {'supported': '有证据支持', 'unknown': '未知', 'not_met': '当前不满足'}
            level_labels = {'required': '必需', 'preferred': '加分', 'context': '待判定'}
            for item in requirements:
                requirement_lines.append('| ' + item['text'].replace('|', '\\|') + ' | ' + level_labels[item['level']] + ' | ' + status_labels[item['status']] + ' | ' + item['reason'].replace('|', '\\|') + ' |')
            requirement_lines += ['', '## 说明', ''] + ['- ' + warning for warning in result['warnings']] + ['- 未生成投递版；未注册投递记录。']
            write(stage / 'match.md', '\n'.join(requirement_lines) + '\n')
            result['files']['match'] = (target / 'match.md').relative_to(case).as_posix()
        else:
            selected, strongest = select(data, family, request['jd'])
            result['selected_bullet_ids'] = [b['id'] for e in selected for b in e['bullets']]
            result['warnings'] += ['本地规则完成方向建议和证据选材；硬门槛、语义关联和版面仍需 Codex / 本人复核。生成成功不代表通过筛选。']
            if re.search(r'合成|synthetic', request['jd'], re.I):
                result['warnings'].append('合成验收样本，不能作为真实招聘岗位投递或计入效果统计。')
            if lang == 'en':
                result['warnings'].append('英文姓名、机构与职务译名使用保守审阅表达；正式外发前复核。')
            lines = text_lines(data['person'], selected, strongest, request['title'], lang, family)
            pdf_name = 'resume-' + lang + '.pdf'
            pdf_checks = render_pdf(stage / pdf_name, lines, font)
            md = '\n\n'.join(('# ' if k == 'name' else '## ' if k == 'section' else '### ' if k == 'job' else '- ' if k == 'bullet' else '') + t for k, t in lines)
            write(stage / ('resume-' + lang + '.md'), md + '\n')
            clauses = positive_clauses(request['jd'])
            match = ['# 岗位匹配审阅', '', '方向：' + FAMILIES[family], '', '这是可审阅的证据关联，不是 ATS 分数或录取概率。', '', '## 硬门槛检查', '', '| 要求 | 层级 | 判断 | 依据与边界 |', '|---|---|---|---|']
            status_labels = {'supported': '有证据支持', 'unknown': '未知', 'not_met': '当前不满足'}
            level_labels = {'required': '必需', 'preferred': '加分', 'context': '待判定'}
            for item in requirements:
                refs = ', '.join(item['evidence_refs']) or '—'
                match.append('| ' + item['text'].replace('|', '\\|') + ' | ' + level_labels[item['level']] + ' | ' + status_labels[item['status']] + ' | ' + item['reason'].replace('|', '\\|') + '；证据：' + refs + ' |')
            match += ['', '## JD 职责与可关联事实', '', '| JD 片段 | 可关联事实 | 判断边界 |', '|---|---|---|']
            for clause in clauses:
                hits = [b['id'] for e in selected for b in e['bullets'] if any(k.lower() in clause.lower() for k in b['keywords'])]
                match.append('| ' + clause.replace('|', '\\|') + ' | ' + (', '.join(hits) if hits else '未找到直接词项证据') + ' | ' + ('词项关联；需核实场景和个人责任' if hits else '未知；不能推定满足') + ' |')
            match += ['', '## 选材与事实来源', '']
            for entry in selected:
                match.append('- ' + entry['title_zh'] + ' → ' + entry['source_ref'] + ' → ' + ', '.join(b['id'] for b in entry['bullets']))
            match += ['', '## 外发前检查', ''] + ['- ' + w for w in result['warnings']]
            match += ['- 硬门槛表只覆盖可识别的明确条目；未列出的职责、行业门槛和语义对应关系仍需要人工审阅。']
            write(stage / 'match.md', '\n'.join(match) + '\n')
            name = data['person']['name_en']
            points = '\n'.join('- ' + b['en'] for _, b in strongest)
            email = 'To: （未提供核实过的招聘邮箱；不发送）\nSubject: Application for ' + request['title'] + ' - ' + name + '\n\nDear Hiring Team,\n\nI am interested in the ' + request['title'] + ' position at ' + request['company'] + '. My relevant experience includes:\n\n' + points + '\n\nI would welcome the opportunity to discuss how this experience could contribute to your team. My resume is attached for your review.\n\nBest regards,\n' + name + '\n' + data['person'].get('email', '') + '\n\nAttachments (local draft): ' + pdf_name + '\n'
            write(stage / 'email.md', email)
            review = ['# 定制说明与面试追问', '', '当前状态：审阅稿；未发送、未提交。', '', '采用方向：' + FAMILIES[family], '选取项目：' + '、'.join(e['title_zh'] for e in selected if e['kind'] == 'project'), '工作经历保留时间线；按本 JD 关键词调整每段要点优先级。', '', '## 每条证据的追问', '']
            for entry in selected:
                for bullet in entry['bullets']:
                    review += ['- ' + bullet['id'] + '：' + bullet['zh'], '  追问：你本人完成了哪一步？能展示什么材料？数字统计范围是什么？哪些是自测、哪些是真实用户结果？']
            review += ['', '## 缓存待确认项（不代表每项都是此 JD 必填）', '', json.dumps(data.get('unconfirmed', []), ensure_ascii=False, indent=2)]
            write(stage / 'review.md', '\n'.join(review) + '\n')
            json_write(stage / 'selection.json', {'family': family, 'selected_bullet_ids': result['selected_bullet_ids'], 'source_digests': data['sources'], 'pdf_checks': pdf_checks, 'routing': routing, 'requirements': requirements, 'requirement_summary': requirements_summary, 'external_actions': []})
            for key, name_ in {'pdf': pdf_name, 'markdown': 'resume-' + lang + '.md', 'match': 'match.md', 'email': 'email.md', 'review': 'review.md'}.items():
                result['files'][key] = (target / name_).relative_to(case).as_posix()
            if url and not existing_package:
                job_key = 'jd-' + hashlib.sha256((request['company'] + '|' + url).encode()).hexdigest()[:20]
                manifest = {'job_key': job_key, 'company': request['company'], 'role': request['title'], 'role_family': family,
                    'resume_variant': family + '-' + run, 'url': url, 'language': lang, 'status': 'preparing',
                    'jd_path': (target / 'jd.md').relative_to(case).as_posix(), 'resume_path': result['files']['pdf'],
                    'email_path': result['files']['email'], 'evidence_refs': [s['path'] for s in data['sources']],
                    'authorization_scope': '', 'unresolved_required_fields': [item['text'] for item in requirements_summary['required_blockers']] + [field + '复核' for field, data_ in metadata_resolution.items() if data_['source'] != 'input'] + ['本人事实及译名复核', '最终版面检查', '投递渠道与授权范围'],
                    'artifacts': [{'path': result['files']['pdf'], 'sha256': sha(stage / pdf_name)}], 'updated_at': datetime.now(timezone.utc).isoformat()}
                json_write(stage / 'manifest.json', manifest)
                result['files']['manifest'] = (target / 'manifest.json').relative_to(case).as_posix()
        json_write(stage / 'result.json', result)
        stage.rename(target)
    except Exception:
        shutil.rmtree(stage)
        raise
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, type=Path)
    parser.add_argument('--request', required=True, type=Path, help='JSON: jd/title/company/url/language/family')
    parser.add_argument('--font')
    args = parser.parse_args()
    try:
        result = generate(args.case, json.loads(args.request.read_text(encoding='utf-8')), args.font)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 2
    return 0

if __name__ == '__main__':
    sys.exit(main())
