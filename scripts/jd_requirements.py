"""Conservative, offline JD requirement extraction and evidence assessment.

This is deliberately a small rules engine. It labels only explicit requirements
that it can recognise; every other phrase stays unknown rather than being
silently inferred from nearby experience.
"""
import re
from datetime import date


def _plain(value):
    return re.sub(r'\s+', ' ', value or '').strip()


def _is_negative(value):
    return bool(re.search(r'不要求|不需要|无需|没有.*要求|未将|不是.*(?:运营|要求|职责)|not required|does not require|no .*required', value, re.I))


def _segments(jd):
    """Return short candidate requirement statements and their explicit level."""
    parts = re.split(r'(?<=[。；;.!?])|\n+', jd)
    level = 'context'
    result = []
    for raw in parts:
        text = _plain(raw)
        if not text or _is_negative(text):
            continue
        lower = text.lower()
        if re.search(r'^(?:工作重点|岗位职责|工作内容|职责|responsibilities?|what you.?ll be doing|employment structure)', text, re.I):
            level = 'context'
        if re.search(r'(^|[：:，, ])(加分|优先|优选|preferred|nice to have|plus)\b|加分项', lower, re.I):
            level = 'preferred'
        elif re.search(r'(^|[：:，, ])(必需|硬性要求|任职要求|职位要求|required|must have|minimum qualifications|you.?ll need to have|qualifications)|(?:至少|\d+以上)\s*\d*\s*(?:年|years?)|(?:minimum of|at least)\s*\d+', lower, re.I):
            level = 'required'
        if re.fullmatch(r'#*\s*(?:you.?ll need to have|minimum qualifications|qualifications|required|任职要求|职位要求)\s*:?', text, re.I):
            continue
        # A requirement marker may prefix several comma-separated conditions.
        candidates = re.split(r'[，、；;]' if re.search(r'[\u4e00-\u9fff]', text) else r'[；;]', text)
        for candidate in candidates:
            candidate = _plain(re.sub(r'^(?:必需|硬性要求|任职要求|职位要求|加分项|加分|优先|preferred|nice to have)\s*[：:]?\s*', '', candidate, flags=re.I))
            if not candidate or _is_negative(candidate):
                continue
            if (level != 'context' or re.search(r'本科|硕士|博士|至少\s*\d+\s*(?:年|years?)|SQL|ERP|工作许可|出差|英语|英文|文档|知识库|结构化|OCR|Prompt|RAG|评测|流程图|操作指南|协作|产品|用户路径|machine learning|pytorch|生产级|distributed', candidate, re.I)):
                result.append((candidate, level))
    # Preserve order but remove duplicates caused by marker segmentation.
    unique = []
    seen = set()
    for text, level in result:
        key = text.lower()
        if key not in seen:
            seen.add(key)
            unique.append((text, level))
    return unique


def _month_index(value):
    match = re.search(r'(\d{4})\.(\d{1,2})', value or '')
    if not match:
        return None
    return int(match.group(1)) * 12 + int(match.group(2)) - 1


def _work_months(entries, tags):
    """Union full-time months; do not double count overlapping roles."""
    months = set()
    for entry in entries:
        if entry.get('kind') != 'work' or '兼职' in entry.get('employment_zh', ''):
            continue
        if not (set(entry.get('tags', [])) & set(tags)):
            continue
        values = re.findall(r'\d{4}\.\d{1,2}', entry.get('dates', ''))
        if len(values) < 2:
            continue
        start, end = _month_index(values[0]), _month_index(values[1])
        if start is not None and end is not None and end >= start:
            months.update(range(start, end + 1))
    return len(months)


def _refs(entries, tag=None, needle=None):
    refs = []
    for entry in entries:
        for bullet in entry.get('bullets', []):
            content = ' '.join([bullet.get('zh', ''), bullet.get('en', ''), ' '.join(bullet.get('keywords', []))])
            if (not tag or tag in bullet.get('tags', []) or tag in entry.get('tags', [])) and (not needle or re.search(needle, content, re.I)):
                refs.append(bullet['id'])
    return refs[:3]


def _item(text, level, status, reason, refs=None):
    return {'text': text, 'level': level, 'status': status, 'reason': reason, 'evidence_refs': refs or []}


def assess(jd, evidence):
    """Assess explicit JD requirements against a checked evidence cache.

    Status is one of supported / unknown / not_met. `not_met` is reserved for
    a clear contradiction in documented facts; omitted evidence is `unknown`.
    """
    if not isinstance(jd, str) or not jd.strip():
        raise ValueError('JD 必须是非空文本')
    if not isinstance(evidence, dict) or not isinstance(evidence.get('person'), dict):
        raise ValueError('证据缓存缺少 person')
    person = evidence['person']
    entries = evidence.get('entries', [])
    if not isinstance(entries, list):
        raise ValueError('证据缓存 entries 格式错误')
    education = ' '.join(str(person.get(key, '')) for key in ('education_zh', 'education_en'))
    output = []
    for text, level in _segments(jd):
        low = text.lower()
        if re.search(r'计算机.*(?:硕士|博士)|(?:硕士|博士).*机器学习|master.?s|phd', text, re.I):
            status = 'not_met' if '本科' in education or 'undergraduate' in education.lower() else 'unknown'
            output.append(_item(text, level, status, '已记录学历为商务英语本科；没有把未提供的相关硕博学历推定为满足。', ['person.education']))
        elif re.search(r'本科|undergraduate|bachelor', text, re.I):
            status = 'supported' if ('本科' in education or 'undergraduate' in education.lower()) else 'unknown'
            output.append(_item(text, level, status, '证据缓存记录了本科教育。' if status == 'supported' else '未找到可核验的本科学历记录。', ['person.education'] if status == 'supported' else []))
        elif re.search(r'(?:至少\s*\d+|minimum of\s*\d+|at least\s*\d+|\d+年以上).*(?:用户|客户|运营|服务|customer|operations|support|account management)', text, re.I):
            years = re.search(r'(?:至少\s*|minimum of\s*|at least\s*)(\d+)|(?:^|\D)(\d+)年以上', text, re.I)
            needed = int(next(group for group in years.groups() if group is not None)) * 12
            got = _work_months(entries, ['user-operations'])
            status = 'supported' if got >= needed else 'not_met'
            output.append(_item(text, level, status, f'已记录的全职用户/服务相关经历按月份并集为 {got} 个月；不与兼职或重叠岗位相加。', _refs(entries, 'user-operations')))
        elif re.search(r'(?:5|五)年.*(?:机器学习|machine learning)|分布式.*(?:模型|训练)|pytorch.*训练|生产级.*模型', text, re.I):
            output.append(_item(text, level, 'not_met', '现有事实库记录的是 AI 内容处理和个人应用实践，不是所述机器学习训练或生产模型经历。', []))
        elif re.search(r'\bSQL\b|\bERP\b|工作许可|work authorization|商务英语|professional fluency|professional.*english|mandarin.*english|native.*english|fluent.*english|英文.*(?:流利|会议|报告)|出差|travel|api.*(?:engineering|technical|沟通)|processing flows|technical errors', text, re.I):
            output.append(_item(text, level, 'unknown', '当前事实库没有可核验的对应能力或意愿；不能从 CET-4、相邻工具或所在地推定。', []))
        elif re.search(r'文档.*(?:清洗|结构化|整理|维护|管理)|内容整理|知识(?:库)?.*(?:整理|维护)|知识库|问答.*(?:生产|整理)|质量检查|prompt|质量意识|文字表达', text, re.I):
            refs = _refs(entries, 'ai-content-operations')
            output.append(_item(text, level, 'supported' if refs else 'unknown', '有文档清洗、结构化、问答整理或质量检查的事实记录。' if refs else '未找到直接事实。', refs))
        elif re.search(r'\bOCR\b|离线评测|AI输出评测|\bRAG\b', text, re.I):
            refs = _refs(entries, 'ai-content-operations')
            output.append(_item(text, level, 'supported' if refs else 'unknown', '有相邻的 OCR、离线评测或 RAG 实践；具体深度仍以事实条目为准。' if refs else '未找到直接事实。', refs))
        elif re.search(r'流程图|操作指南|多方协作|协调多方|跨团队|沟通.*文档|文档.*沟通|项目.*(?:跟进|进度|交付)|实施', text, re.I):
            refs = _refs(entries, 'implementation-support')
            output.append(_item(text, level, 'supported' if refs else 'unknown', '有流程图、指南、问题跟进或多方协调事实记录。' if refs else '未找到直接事实。', refs))
        elif re.search(r'可交互.*(?:方案|项目)|用户路径|信息(?:架构|分类)|需求文档|产品.*(?:项目|实践)', text, re.I):
            refs = _refs(entries, 'product-operations')
            output.append(_item(text, level, 'supported' if refs else 'unknown', '有个人项目中的用户路径、分类、可交互交付或产品边界事实记录。' if refs else '未找到直接事实。', refs))
        else:
            output.append(_item(text, level, 'unknown', '本地规则无法可靠判断该要求；需由 Codex 或候选人核实。', []))
    return output


def summary(items):
    counts = {status: sum(1 for item in items if item['status'] == status) for status in ('supported', 'unknown', 'not_met')}
    required_blockers = [item for item in items if item['level'] == 'required' and item['status'] != 'supported']
    return {'counts': counts, 'required_blockers': required_blockers, 'ready_for_human_review': not required_blockers}
