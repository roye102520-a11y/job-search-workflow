"""Conservative offline requirements: supported / partial / unknown / not_met."""
import re
from datetime import date
from evidence_quality import usable_entries, positive_clauses
from foreign_eligibility import check as foreign_checks


def _plain(value):
    return re.sub(r'\s+', ' ', value or '').strip()


def _requirement_categories(text):
    categories = set()
    if re.search(r'本科|bachelor|undergraduate|硕士|master|博士|phd|doctorate|degree', text, re.I):
        categories.add('degree')
    if re.search(r'在校|在读|enrolled|student|graduat(?:e|ing|ion)|毕业|届', text, re.I):
        categories.add('student_or_graduation')
    if re.search(r'工作许可|work authori[sz]ation|right to work|visa|签证', text, re.I):
        categories.add('work_authorization')
    if re.search(r'英语|英文|english|mandarin|chinese|日语|japanese|language proficiency|语言能力', text, re.I):
        categories.add('language')
    if re.search(r'\d+\s*(?:年|years?)|years? of experience|经验年限', text, re.I):
        categories.add('experience_years')
    if re.search(r'\b(?:paid|unpaid|salary|compensation|薪资|工资|无薪|有薪)\b|薪酬', text, re.I):
        categories.add('compensation')
    return categories


def _atomic_conditions(text):
    """Split independent hard conditions while keeping alternatives intact."""
    parts = re.split(r'\s+(?:and|&|及|以及|并且)\s+', text, flags=re.I)
    if len(parts) < 2:
        return [text]
    categories = [_requirement_categories(part) for part in parts]
    all_categories = set().union(*categories)
    if len(all_categories) > 1 and all(categories):
        return [part.strip() for part in parts if part.strip()]
    return [text]


def _segments(jd):
    level, output, seen = 'context', [], set()
    required_headings = (
        r'requirements?|qualifications?|must have|minimum qualifications|you.?ll need to have',
        r'what you(?:\'|’)ll bring|what we(?:\'|’)re looking for|who you are|your profile',
        r'mandatory requirements?|任职要求|职位要求|岗位要求|任职资格|必备条件',
    )
    preferred_headings = (r'preferred qualifications?|preferred|nice to have|加分项|优先条件',)
    context_headings = (
        r'responsibilities|job responsibilities|duties|what you(?:\'|’)ll do|what you(?:\'|’)ll be doing',
        r'job description|about the role|role overview|what you(?:\'|’)ll build|key responsibilities',
        r'about us|about the company|company description|who we are|what we offer|work benefits|benefits|vendor type|equal employment opportunity|application (?:form|questions?)|how to apply|privacy policy|工作职责|职位描述|工作内容|福利|工作福利|申请流程|申请表',
    )
    for raw in re.split(r'[。；;\n!?！？]+', jd):
        text = _plain(raw)
        if not text:
            continue
        text = re.sub(r'^#+\s*', '', text).strip()
        heading_match = None
        for patterns, section_level in ((preferred_headings, 'preferred'), (required_headings, 'required'), (context_headings, 'context')):
            for pattern in patterns:
                heading_match = re.match(r'^(?:' + pattern + r')\s*[:：]?\s*(.*)$', text, re.I)
                if heading_match:
                    level = section_level
                    remainder = heading_match.group(1).strip()
                    if not remainder:
                        text = ''
                    else:
                        text = remainder
                    break
            if heading_match:
                break
        if not text:
            continue
        # English comma lists remain one condition; Chinese comma clauses can carry their own marker.
        for part in re.split(r'[，]' if re.search(r'[\u4e00-\u9fff]', text) else r'(?!)', text):
            if re.search(r'加分|优先|优选|preferred|nice to have|\bplus\b', part, re.I):
                item_level = 'preferred'
                if re.match(r'^(?:加分|优先|preferred|nice to have)', part, re.I):
                    level = item_level
            elif re.search(r'必需|硬性要求|任职要求|职位要求|岗位要求|必须|\brequired\b|must have|minimum qualifications|at least|至少|\d+年以上', part, re.I):
                item_level = level = 'required'
            else:
                item_level = level
            # Split enumeration unless it expresses alternatives.
            chunks = re.split(r'、', part)
            for chunk in chunks:
                if not positive_clauses(chunk):
                    continue
                condition = re.sub(r'^\s*(?:#+\s*)?(?:必需|硬性要求|任职要求|职位要求|岗位要求|岗位职责|工作内容|职责|加分项|加分|优先|required|preferred|nice to have|minimum qualifications|qualifications|you.?ll need to have)\s*[:：]?\s*', '', chunk, flags=re.I).strip()
                if not condition:
                    continue
                if item_level != 'context' or re.search(r'本科|硕士|博士|SQL|ERP|工作许可|出差|英语|文档|知识库|OCR|Prompt|RAG|评测|流程|协作|产品|pytorch|生产级|在校|在读|毕业|student|enrolled|graduate|salary|compensation|unpaid|paid|years? of experience', condition, re.I):
                    for atom in _atomic_conditions(condition):
                        if atom.lower() not in seen:
                            output.append((atom, item_level)); seen.add(atom.lower())
    return output


def _work_months(entries, tags):
    months, refs, invalid = set(), [], False
    for entry in entries:
        if entry.get('kind') != 'work' or re.search(r'兼职|part.time|实习|intern', entry.get('employment_zh', '') + entry.get('employment_en', ''), re.I):
            continue
        if not set(entry.get('tags', [])) & set(tags) or not entry.get('bullets'):
            continue
        dates = re.findall(r'(\d{4})[.\-/](\d{1,2})(?!\d)', entry.get('dates', ''))
        if len(dates) != 2 or any(not 1 <= int(m) <= 12 for _, m in dates):
            invalid = True; continue
        start, end = [int(y) * 12 + int(m) - 1 for y, m in dates]
        if end < start:
            invalid = True; continue
        now = date.today().year * 12 + date.today().month - 1
        if start > now:
            invalid = True; continue
        months.update(range(start, min(end, now) + 1))
        refs.extend(b['id'] for b in entry['bullets'])
    return len(months), refs, invalid


CONCEPTS = [
    (r'\bSQL\b', r'\bSQL\b', None), (r'\bERP\b', r'\bERP\b', 'implementation-support'),
    (r'\bOCR\b', r'\bOCR\b', 'ai-content-operations'), (r'\bRAG\b', r'\bRAG\b|检索.*(?:原型|引用)|retrieval', 'ai-content-operations'),
    (r'prompt|提示词', r'prompt|提示词', 'ai-content-operations'),
    (r'离线评测|AI输出评测|offline evaluation', r'离线.*(?:评测|样本)|offline.*(?:evaluation|examples)', 'ai-content-operations'),
    (r'知识库|问答', r'知识库|问答|knowledge base|question.and.answer', 'ai-content-operations'),
    (r'文档.*(?:清洗|结构化|整理|维护|管理)|内容整理|结构化', r'清洗|结构化|structured|cleaned|文档管理|维护内容版本', 'ai-content-operations'),
    (r'质量检查|质量意识', r'质量|复核|校对|quality|checked|review', 'ai-content-operations'),
    (r'流程图|操作指南|操作手册', r'流程图|操作卡|指南|操作手册|instruction|guide', 'implementation-support'),
    (r'多方协作|协调多方|跨团队|多方协调', r'协调|协作|coordinat|stakeholder', 'implementation-support'),
    (r'项目.*(?:跟进|进度|交付)|实施', r'进度|交付|工单|跟进|progress|deliver|ticket|follow.up', 'implementation-support'),
    (r'用户路径|信息(?:架构|分类)|需求文档|产品.*(?:项目|实践)|可交互', r'用户路径|分类|需求|可交互|user journey|information architecture|product scope', 'product-operations'),
    (r'用户.*(?:沟通|服务|运营)|客户.*(?:沟通|服务|成功|运营)', r'参与者|用户|客户|registrant|participant|customer|client', 'user-operations'),
]


def assess(jd, evidence):
    if not isinstance(jd, str) or not jd.strip():
        raise ValueError('JD 必须是非空文本')
    if not isinstance(evidence, dict) or not isinstance(evidence.get('person'), dict):
        raise ValueError('证据缓存缺少 person')
    if not isinstance(evidence.get('entries', []), list):
        raise ValueError('证据缓存 entries 格式错误')
    person, entries = evidence['person'], usable_entries(evidence)
    index = {b['id']: {'id': b['id'], 'source_ref': e.get('source_ref', ''), 'text': b.get('zh', ''), 'kind': e.get('kind', 'unknown')}
             for e in entries for b in e['bullets']}
    education = ' '.join(str(person.get(k, '')) for k in ('education_zh', 'education_en')).strip()
    education_pending = any(isinstance(item, dict) and item.get('field', item.get('id')) in {'person.education', 'person.education_zh', 'education'} for item in evidence.get('unconfirmed', []))
    if education_pending or person.get('education_status') in {'unconfirmed', 'conflict', 'pending'}:
        education = ''
    index['person.education'] = {'id': 'person.education', 'source_ref': person.get('education_source_ref', 'resume-evidence.json#person.education'), 'text': education, 'kind': 'education'}
    output = []
    for text, level in _segments(jd):
        status, reason, refs = 'unknown', '未找到足够的直接证据；请人工复核，缺失不代表不具备。', []
        degree = re.search(r'本科|bachelor|undergraduate|硕士|master|博士|phd|doctorate', text, re.I)
        years = re.search(r'(?:至少\s*|minimum of\s*|at least\s*)(\d+)\s*(?:年|years?)|(?:^|\D)(\d+)\s*年以上', text, re.I)
        if degree:
            want = 3 if re.search(r'博士|phd|doctorate', text, re.I) and not re.search(r'硕士|master', text, re.I) else 2 if re.search(r'硕士|master', text, re.I) else 1
            got = 3 if re.search(r'博士|phd|doctorate', education, re.I) else 2 if re.search(r'硕士|master', education, re.I) else 1 if re.search(r'本科|bachelor|undergraduate', education, re.I) else 0
            if education:
                refs = ['person.education']
                status = 'supported' if got >= want else 'not_met' if person.get('education_complete') is True and got else 'unknown'
                reason = '当前学历记录：' + education + '；仅完整且已确认的学历记录可证明不满足。'
                if status == 'supported' and re.search(r'在读|预计|未毕业|currently studying|expected', education, re.I):
                    status, reason = 'partial', reason + ' 学历完成状态尚未证明。'
                major = re.search(r'计算机|机器学习|computer science|machine learning', text, re.I)
                if status == 'supported' and major and not re.search(r'计算机|机器学习|computer science|machine learning', education, re.I):
                    status, reason = 'partial', reason + ' 学历层级有证据，专业要求需单独确认。'
        elif years and re.search(r'用户|客户|运营|服务|customer|operations|support|account management', text, re.I):
            needed = int(next(g for g in years.groups() if g)) * 12
            got, refs, invalid = _work_months(entries, ['user-operations'])
            status = 'supported' if got >= needed else 'not_met' if person.get('experience_complete') is True and not invalid else 'partial' if got else 'unknown'
            reason = f'已记录的全职用户/服务相关经历按月份并集为 {got} 个月；不累加兼职或重叠岗位。' + ('经历完整性已确认。' if person.get('experience_complete') is True else '经历完整性未确认，不能据此断定不满足。')
        elif re.search(r'出差|travel|英语|english', text, re.I):
            key = 'travel' if re.search(r'出差|travel', text, re.I) else 'professional_english'
            fact = person.get('capabilities', {}).get(key, {})
            if isinstance(fact, dict) and fact.get('status') == 'confirmed' and isinstance(fact.get('value'), bool) and fact.get('source_ref'):
                status = 'supported' if fact['value'] else 'not_met'
                ref = 'person.capabilities.' + key
                index[ref] = {'id': ref, 'source_ref': fact['source_ref'], 'text': str(fact['value']), 'kind': 'profile'}; refs = [ref]
                reason = '使用本人确认的当前能力/意愿记录；外发前复核适用范围。'
        else:
            conditions = [(needle, tag) for trigger, needle, tag in CONCEPTS if re.search(trigger, text, re.I)]
            parts, all_refs = [], []
            strict = bool(re.search(r'生产级|生产环境|独立负责|熟练|精通|production|expert|proficien', text, re.I))
            for needle, tag in conditions:
                direct, adjacent = [], []
                for entry in entries:
                    for bullet in entry['bullets']:
                        content = bullet.get('zh', '') + ' ' + bullet.get('en', '')
                        if re.search(needle, content, re.I):
                            direct.append(bullet['id'])
                        elif tag and tag in set(entry.get('tags', []) + bullet.get('tags', [])):
                            adjacent.append(bullet['id'])
                chosen = direct or adjacent
                complete_depth = direct and (not strict or any(re.search(r'生产级|生产环境|独立负责|熟练|精通|production|expert|proficien', ' '.join(positive_clauses(index[r]['text'])), re.I) for r in direct))
                parts.append('supported' if complete_depth else 'partial' if chosen else 'unknown')
                all_refs.extend(chosen)
            if parts:
                # A compound statement is fully supported only when every condition is proved.
                status = 'supported' if all(p == 'supported' for p in parts) else 'partial' if any(p != 'unknown' for p in parts) else 'unknown'
                refs = list(dict.fromkeys(all_refs))
                reason = '逐项找到直接表述。' if status == 'supported' else '仅部分条件或相邻实践有证据；场景、熟练度和完整责任尚未证明。'
        # A degree in a compound statement must not hide another hard condition.
        if degree and (years or any(re.search(trigger, text, re.I) for trigger, _, _ in CONCEPTS) or re.search(r'工作许可|出差|英语|english|travel|work authorization', text, re.I)):
            remaining = re.sub(r'本科|bachelor(?:[’\']s)?|undergraduate|硕士|master(?:[’\']s)?|博士|phd|doctorate', '', text, flags=re.I)
            extra = assess('任职要求：' + remaining, evidence)
            if extra:
                if status != 'not_met' and any(i['status'] != 'supported' for i in extra):
                    status = 'partial' if refs or any(i['evidence_refs'] for i in extra) else 'unknown'
                if status == 'unknown' and any(i['evidence_refs'] for i in extra):
                    status = 'partial'
                index.update({ref['id']: ref for item in extra for ref in item.get('evidence', [])})
                refs = list(dict.fromkeys(refs + [ref for i in extra for ref in i['evidence_refs']]))
                reason += ' 同条中的其余条件分别核对，不能由学历覆盖。'
        eligibility = foreign_checks(text, person)
        if eligibility:
            states = [item['status'] for item in eligibility]
            if status == 'not_met' or 'not_met' in states:
                status = 'not_met'
            elif any(s != 'supported' for s in states):
                status = 'partial' if refs or any(item['evidence'] for item in eligibility) else 'unknown'
            elif not degree:
                status = 'supported'
            for item in eligibility:
                reason += ' ' + item['reason']
                for proof in item['evidence']:
                    index[proof['id']] = proof
                    if proof['id'] not in refs:
                        refs.append(proof['id'])
        output.append({'text': text, 'level': level, 'status': status, 'reason': reason,
                       'evidence_refs': refs, 'evidence': [index[r] for r in refs if r in index], 'human_review_required': True})
    return output


def summary(items):
    counts = {s: sum(i['status'] == s for i in items) for s in ('supported', 'partial', 'unknown', 'not_met')}
    blockers = [i for i in items if i['level'] == 'required' and i['status'] != 'supported']
    return {'counts': counts, 'required_blockers': blockers, 'ready_for_human_review': not blockers}
