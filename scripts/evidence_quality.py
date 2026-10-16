"""Shared evidence eligibility. Additive fields keep schema v1 caches readable."""
import re

UNSAFE = {'unconfirmed', 'pending', 'needs_review', 'conflict', 'disputed', 'rejected', 'excluded'}


def exclusion_reason(data, entry, bullet=None):
    for item in (entry, bullet or {}):
        status = item.get('confirmation_status', item.get('status', 'confirmed'))
        if status in UNSAFE or item.get('confirmed') is False:
            return '待确认或已排除的事实，不进入材料'
        if item.get('conflict') or item.get('conflicts'):
            return '存在未解决的事实冲突'
    # Do not let an unconfirmed item with no identifier match the absent
    # identifier on every entry. This previously excluded the entire evidence
    # bank whenever it contained ordinary field-level review notes.
    ids = {value for value in (entry.get('id'), (bullet or {}).get('id'))
           if isinstance(value, str) and value}
    for item in data.get('unconfirmed', []):
        if not isinstance(item, dict):
            continue
        refs = item.get('evidence_refs', [])
        item_ids = (item.get('id'), item.get('entry_id'), item.get('bullet_id'))
        if (any(value in ids for value in item_ids if isinstance(value, str) and value)
                or any(ref in ids for ref in refs if isinstance(ref, str) and ref)):
            return '事实库待确认项引用了这条证据'
        if item.get('field') == 'projects.start_date_conflict' and entry.get('kind') == 'project':
            return '项目日期冲突，确认后再使用'
    if bullet and re.search(r'待确认|needs confirmation|\[TODO\]|\{\{', bullet.get('zh', '') + bullet.get('en', ''), re.I):
        return '表述含待确认占位内容'
    return ''


def usable_entries(data):
    return [{**entry, 'bullets': [b for b in entry.get('bullets', []) if not exclusion_reason(data, entry, b)]}
            for entry in data.get('entries', []) if not exclusion_reason(data, entry)]


def positive_clauses(text):
    # Clause-level negation avoids discarding a positive condition after a comma.
    negative = r'不要求|不需要|无需|无.{0,8}要求|不是|未将|not required|does not require|no .{0,40}required|not responsible for|没有生产|无生产|未.{0,8}(?:生产|上线)|no production|not.{0,20}production'
    return [s.strip() for s in re.split(r'[。；;\n，,!?！？]', text)
            if s.strip() and not re.search(negative, s, re.I)]
