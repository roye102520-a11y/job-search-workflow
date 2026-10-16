"""Sourced, conservative early-career eligibility checks, shared by JD review.

Graduation does not prove current non-enrolment. A country-neutral permission
boolean cannot prove a right to work in a particular jurisdiction.
"""
import re
from datetime import date


def check(text, person):
    checks = []

    def add(kind, status, reason, ref='', value=''):
        checks.append({'kind': kind, 'status': status, 'reason': reason,
                       'evidence': [{'id': 'person.' + kind, 'source_ref': ref, 'text': str(value)}] if ref else []})

    student = re.search(r'在校生|在读|current(?:ly)?\s+(?:enrolled|studying|university student|student)|enrolled in|return(?:ing)? to (?:university|school)|must be a student', text, re.I)
    if student:
        fact = person.get('enrollment', {})
        valid = isinstance(fact, dict) and fact.get('status') == 'confirmed' and fact.get('source_ref')
        value = fact.get('value') if valid else None
        add('enrollment', 'supported' if value == 'enrolled' else 'not_met' if value == 'not_enrolled' else 'unknown',
            '需当前在校资格证据；已毕业本身不能证明现在是否在读。', fact.get('source_ref', '') if valid else '', value)

    graduation = re.search(r'graduat(?:e|es|ed|ing|ion)|毕业|届', text, re.I)
    years = [int(y) for y in re.findall(r'\b20\d{2}\b', text)] if graduation else []
    if years:
        value = person.get('graduation_date', '')
        ref = person.get('graduation_source_ref', '')
        known = bool(ref and re.fullmatch(r'20\d{2}-(?:0[1-9]|1[0-2])(?:-\d{2})?', value))
        actual = int(value[:4]) if known else None
        allowed = set(range(min(years), max(years) + 1)) if re.search(r'between|至|到|20\d{2}\s*[-–—]', text, re.I) else set(years)
        # Month/day windows need a separate review even when the year agrees.
        precise = bool(re.search(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)|20\d{2}[-/.]\d|\d+月', text, re.I))
        status = 'not_met' if known and actual not in allowed else 'unknown' if not known or precise else 'supported'
        add('graduation_date', status, '按 JD 毕业年份核对；月份窗口或缺少来源时保持待确认。', ref if known else '', value)

    if re.search(r'工作许可|work authori[sz]ation|right to work|legally authori[sz]ed|visa sponsorship|签证担保', text, re.I):
        countries = []
        for code, pattern in [('CN', r'\bChina\b|中国'), ('GB', r'\bUK\b|United Kingdom|英国'),
                              ('US', r'\bUS\b|\bUSA\b|United States|美国'), ('SG', r'Singapore|新加坡')]:
            if re.search(pattern, text, re.I):
                countries.append(code)
        fact = person.get('capabilities', {}).get('work_authorization', {})
        valid = isinstance(fact, dict) and fact.get('status') == 'confirmed' and fact.get('source_ref')
        scoped = valid and len(countries) == 1 and countries[0] in fact.get('countries', [])
        expiry = fact.get('valid_until') if valid else None
        if expiry:
            try:
                scoped = scoped and date.fromisoformat(expiry) >= date.today()
            except ValueError:
                scoped = False
        value = fact.get('value') if scoped else None
        # Sponsorship and permit are distinct claims, even in the same sentence.
        status = 'supported' if value is True else 'not_met' if value is False else 'unknown'
        if re.search(r'sponsor|担保', text, re.I):
            status = 'unknown'
        add('work_authorization', status, '工作许可必须对应国家、有效期和雇佣范围；不跨地区复用，也不推断担保条件。',
            fact.get('source_ref', '') if scoped else '', value)
    return checks
