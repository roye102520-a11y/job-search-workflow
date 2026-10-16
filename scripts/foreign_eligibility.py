"""Sourced, conservative early-career eligibility checks, shared by JD review.

Graduation does not prove current non-enrolment. A country-neutral permission
boolean cannot prove a right to work in a particular jurisdiction.
"""
import re
from datetime import date

COUNTRIES = (
    ('CN', r'\bChina\b|中国|mainland China|PRC'),
    ('GB', r'\bUK\b|United Kingdom|英国|Great Britain'),
    ('US', r'\bUS\b|\bUSA\b|United States|美国'),
    ('SG', r'Singapore|新加坡'),
    ('MY', r'Malaysia|马来西亚'),
    ('TW', r'Taiwan|台湾'),
    ('HK', r'Hong Kong|香港'),
    ('CA', r'Canada|加拿大'),
    ('AU', r'Australia|澳大利亚'),
    ('JP', r'Japan|日本'),
    ('IN', r'India|印度'),
    ('DE', r'Germany|德国'),
    ('FR', r'France|法国'),
    ('IE', r'Ireland|爱尔兰'),
    ('AE', r'United Arab Emirates|\bUAE\b|阿联酋'),
)


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
        countries = [code for code, pattern in COUNTRIES if re.search(pattern, text, re.I)]
        fact = person.get('capabilities', {}).get('work_authorization', {})
        valid = (isinstance(fact, dict) and fact.get('status') == 'confirmed'
                 and isinstance(fact.get('value'), bool) and isinstance(fact.get('source_ref'), str)
                 and bool(fact.get('source_ref')))
        supported_countries = fact.get('countries', []) if valid else []
        if not isinstance(supported_countries, list):
            supported_countries = []
        expiry_valid = True
        expiry = fact.get('valid_until') if valid else None
        if expiry:
            try:
                expiry_valid = date.fromisoformat(expiry) >= date.today()
            except (TypeError, ValueError):
                expiry_valid = False
        # A negative answer for one country says nothing about another. If a JD
        # names several countries, evaluate every one and leave unscoped facts unknown.
        targets = countries or ['unspecified']
        for country in targets:
            scoped = valid and country != 'unspecified' and country in supported_countries and expiry_valid
            value = fact.get('value') if scoped else None
            status = 'supported' if value is True else 'not_met' if value is False else 'unknown'
            kind = 'work_authorization' if country == 'unspecified' else 'work_authorization_' + country
            add(kind, status,
                '工作许可须有当前、可追溯且对应工作地区的证据；其他地区的许可记录不参与判断。',
                fact.get('source_ref', '') if scoped else '', value)
    return checks
