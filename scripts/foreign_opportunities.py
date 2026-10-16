"""Read-only official job discovery. Local manifests/tracker remain the only job store.

No authentication, applicant data, mail, uploads, form filling or submission.
Only reviewed public employer/ATS tenants are fetched; a client cannot assert
verification. HTTP 200 alone never proves that a particular job is open.
"""
import argparse
import hashlib
import ipaddress
import json
import re
import socket
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urljoin, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

import job_data as records
from career_workspace import local_file, read_json
from jd_requirements import assess

MAX_BYTES = 2 * 1024 * 1024
SCORE_LABEL = '规则识别的证据覆盖分，不是录取概率；所有结果均需人工复核'
MATCH_RULES_VERSION = '2026-10-16.2'
# Exact tenants, never a wildcard such as *.myworkdayjobs.com.
LEVER = {'weloglobal': 'Welo Global', 'getwingapp': 'Wing Assistant', 'veeva': 'Veeva Systems'}
WORKDAY = {'cerence.wd5.myworkdayjobs.com': ('cerence', 'Cerence', 'Cerence'),
           'sanofi.wd3.myworkdayjobs.com': ('sanofi', 'SanofiCareers', 'Sanofi'),
           'lighting.wd3.myworkdayjobs.com': ('lighting', 'jobs-and-careers', 'Signify')}


class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.text = []; self.skip = 0; self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {'script', 'style'}:
            self.skip += 1
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag in {'p', 'li', 'h1', 'h2', 'h3', 'br', 'div'} and not self.skip:
            self.text.append('\n')

    def handle_endtag(self, tag):
        if tag in {'script', 'style'}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)


def plain(html):
    page = Page(); page.feed(html or '')
    return '\n'.join(' '.join(line.split()) for line in ''.join(page.text).splitlines() if line.strip())


def source(url):
    """Resolve only a reviewed public posting, not a user-selected network host."""
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('请提供官方岗位链接')
    p = urlsplit(url)
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
        raise ValueError('仅支持无凭据的 HTTPS 官方岗位链接')
    host, path = p.hostname, p.path
    if host == 'jobs.lever.co':
        parts = path.strip('/').split('/')
        if len(parts) == 2 and parts[0] in LEVER and re.fullmatch(r'[a-f0-9-]{36}', parts[1]):
            tenant, ident = parts
            return dict(company=LEVER[tenant], namespace='lever:' + tenant, requisition_id=ident,
                        adapter='lever', fetch_url=f'https://api.lever.co/v0/postings/{tenant}/{ident}')
    if host in WORKDAY:
        tenant, site, company = WORKDAY[host]
        match = re.search(r'/job/(.+)$', path)
        prefix = path.split('/job/')[0].strip('/').split('/')
        if match and prefix[-1:] == [site] and not re.search(r'\.\.|%2e|%2f', path, re.I):
            return dict(company=company, namespace='workday:' + tenant, requisition_id='', adapter='workday',
                        fetch_url=f'https://{host}/wday/cxs/{tenant}/{site}/job/{match[1]}')
    if host == 'jobs.smartrecruiters.com' and re.fullmatch(r'/BoschGroup/\d+(?:-[^/]*)?/?', path):
        ident = re.search(r'/BoschGroup/(\d+)', path)[1]
        return dict(company='Bosch Group', namespace='smartrecruiters:BoschGroup', requisition_id=ident,
                    adapter='smartrecruiters', fetch_url=f'https://api.smartrecruiters.com/v1/companies/BoschGroup/postings/{ident}')
    if host in {'jobs.sap.com', 'careers.sap.com'} and ('/job/' in path or re.match(r'/en/jobs/\d+/', path)):
        return dict(company='SAP', namespace='sap', requisition_id='', adapter='html', fetch_url=url)
    if host == 'jobs.ikea.com' and path.startswith('/en/job/'):
        return dict(company='IKEA', namespace='ikea', requisition_id='', adapter='html', fetch_url=url)
    raise ValueError('尚未支持此官方域名或 ATS 租户；可在 JD Studio 手动分析，不能标记已核验')


def network_url(url):
    p = urlsplit(url)
    hosts = {'api.lever.co', 'api.smartrecruiters.com', 'jobs.smartrecruiters.com', 'jobs.sap.com', 'careers.sap.com', 'jobs.ikea.com', *WORKDAY}
    if p.scheme != 'https' or p.hostname not in hosts or p.username or p.password or p.port not in (None, 443):
        raise ValueError('拒绝非官方重定向或网络地址')
    addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('拒绝非公网地址')


class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        network_url(newurl)
        if urlsplit(req.full_url).hostname != urlsplit(newurl).hostname:
            raise ValueError('跨域跳转需要人工核验')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    network_url(url)
    request = Request(url, headers={'User-Agent': 'CareerStudio/1.0 (read-only job research)', 'Accept': 'application/json,text/html'})
    with build_opener(Redirects()).open(request, timeout=15) as response:
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('官方页面超过读取上限，需人工核验')
        return response.status, response.url, raw.decode('utf-8')


def parse(url, body):
    origin = source(url)
    row = dict(url=url, company=origin['company'], employer_namespace=origin['namespace'],
               requisition_id=origin['requisition_id'], title='', jd='', location='未知',
               employment_type='未知', posted_date=None, posted_date_text='未知', apply_url='', accepting=False)
    if origin['adapter'] == 'lever':
        data = json.loads(body)
        row.update(title=data.get('text', ''), requisition_id=data.get('id', origin['requisition_id']),
                   location=data.get('categories', {}).get('location', '未知'),
                   employment_type=data.get('categories', {}).get('commitment', '未知'),
                   apply_url=data.get('applyUrl', ''),
                   compensation=data.get('salaryRange') or data.get('salary') or data.get('compensation') or '')
        row['jd'] = '\n'.join([data.get('descriptionPlain', '')] +
                             [item.get('text', '') + '\n' + plain(item.get('content', '')) for item in data.get('lists', [])] +
                             [data.get('additionalPlain', '')]).replace('\\n', '\n').strip()
        row['accepting'] = bool(row['title'] and row['jd'] and row['apply_url'])
    elif origin['adapter'] == 'workday':
        data = json.loads(body).get('jobPostingInfo', {})
        row.update(title=data.get('title', ''), jd=plain(data.get('jobDescription', '')),
                   requisition_id=data.get('jobReqId', ''), location=data.get('location', '未知'),
                   employment_type=data.get('timeType', '未知'), posted_date_text=data.get('postedOn', '未知'),
                   compensation=data.get('compensation') or data.get('salaryRange') or data.get('salary') or '')
        posted = data.get('startDate', '')
        row['posted_date'] = posted if re.fullmatch(r'\d{4}-\d{2}-\d{2}', posted) else None
        row['accepting'] = data.get('canApply') is True
        row['closed'] = data.get('canApply') is False or data.get('posted') is False
        row['apply_url'] = url if row['accepting'] else ''
    elif origin['adapter'] == 'smartrecruiters':
        data = json.loads(body)
        location = data.get('location') if isinstance(data.get('location'), dict) else {}
        employment = data.get('typeOfEmployment') if isinstance(data.get('typeOfEmployment'), dict) else {}
        job_ad = data.get('jobAd') if isinstance(data.get('jobAd'), dict) else {}
        sections = job_ad.get('sections', [])
        if isinstance(sections, dict): sections = list(sections.values())
        jd_parts = []
        if isinstance(sections, list):
            for section in sections:
                if not isinstance(section, dict): continue
                title = str(section.get('title') or '').strip()
                content = plain(str(section.get('text') or section.get('content') or ''))
                if content and not re.search(r'company description|about the company', title, re.I):
                    jd_parts.append(('## ' + title + '\n' if title else '') + content)
        active = data.get('active') is True
        apply_url = data.get('applyUrl', '')
        posting_url = data.get('postingUrl', '')
        row.update(title=data.get('name') or data.get('title') or '',
                   requisition_id=str(data.get('id') or data.get('refNumber') or origin['requisition_id']),
                   jd='\n\n'.join(jd_parts),
                   location=', '.join(str(location[k]) for k in ('city', 'region', 'country') if location.get(k)) or '未知',
                   employment_type=employment.get('label') or employment.get('id') or '未知',
                   posted_date_text=data.get('releasedDate') or '未知',
                   compensation=data.get('compensation') or data.get('salaryRange') or data.get('salary') or '',
                   apply_url=apply_url if isinstance(apply_url, str) else '')
        released = str(data.get('releasedDate') or '')
        row['posted_date'] = released[:10] if re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:T.*)?', released) else None
        row['accepting'] = active and bool(row['jd']) and bool(row['title']) and bool(row['apply_url'])
        row['closed'] = data.get('active') is False
        row['posting_url'] = posting_url if isinstance(posting_url, str) else ''
    else:
        # Structured JobPosting avoids treating a careers landing page as the JD.
        postings = []
        def collect(value):
            if isinstance(value, list):
                for item in value: collect(item)
            elif isinstance(value, dict):
                if value.get('@type') == 'JobPosting': postings.append(value)
                if '@graph' in value: collect(value['@graph'])
        for script in re.findall(r'<script\b[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>', body, re.S | re.I):
            try: collect(json.loads(script))
            except ValueError: continue
        if len(postings) == 1:
            data = postings[0]
            loc = data.get('jobLocation', {})
            if isinstance(loc, list): loc = loc[0] if loc else {}
            address = loc.get('address', {}) if isinstance(loc, dict) else {}
            if isinstance(address, dict):
                row['location'] = ', '.join(str(address[k]) for k in ('addressLocality', 'addressRegion', 'addressCountry') if address.get(k)) or '未知'
            row.update(title=data.get('title', ''), jd=plain(data.get('description', '')),
                       employment_type=data.get('employmentType', '未知'), compensation=data.get('baseSalary') or data.get('salary') or '')
            identifier = data.get('identifier', {})
            row['requisition_id'] = str(identifier.get('value', row['requisition_id'])) if isinstance(identifier, dict) else str(identifier)
            posted = data.get('datePosted', '')
            row['posted_date'] = posted[:10] if re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:T.*)?', posted) else None
            expiry = data.get('validThrough', '')
            row['expired'] = bool(re.match(r'^\d{4}-\d{2}-\d{2}', expiry) and expiry[:10] < datetime.now(timezone.utc).date().isoformat())
            page = Page(); page.feed(body)
            row['accepting'] = bool(re.search(r"apply now|apply for this job|I'm interested|我要申请|立即申请", plain(body), re.I)) and not row['expired']
            row['apply_url'] = url if row['accepting'] else ''
    return row


def observe(url, transport=None):
    origin = source(url)  # Unsupported inputs cannot be verified by imported flags.
    checked = records.now()
    row = dict(url=url, company=origin['company'], employer_namespace=origin['namespace'],
               requisition_id=origin['requisition_id'], title='岗位待核实', jd='', location='未知', employment_type='未知',
               posted_date=None, posted_date_text='未知', apply_url='')
    verification = dict(status='unknown', checked_at=checked, verified_at=None, source_url=url, method='official_http_get')
    body = ''
    try:
        code, final, body = (transport or fetch)(origin['fetch_url'])
        verification.update(http_status=code, final_url=final)
        if code != 200:
            verification['status'] = 'closed' if code in {404, 410} else 'unknown'
        elif records.canonical(final) != records.canonical(origin['fetch_url']):
            verification['reason'] = '跳转离开原职位地址；不把通用招聘页视为有效 JD'
        else:
            row.update(parse(url, body))
            verification['status'] = 'verified_open' if len(row['jd']) >= 40 and row['title'] and row['accepting'] else 'closed' if row.get('expired') or row.get('closed') else 'unknown'
            if verification['status'] == 'verified_open': verification['verified_at'] = checked
    except HTTPError as error:
        verification.update(http_status=error.code, status='closed' if error.code in {404, 410} else 'unknown', reason='官方页面返回 HTTP ' + str(error.code))
    except (ValueError, OSError, URLError, KeyError, TypeError) as error:
        verification['reason'] = '读取未完成：' + type(error).__name__
    verification['content_sha256'] = hashlib.sha256(body.encode()).hexdigest()
    row['verification'] = verification
    row['_body'] = body
    return row


def employment_category(job):
    """Normalize the stated contract type without inferring missing details."""
    title = str(job.get('title') or '')
    stated = str(job.get('employment_type') or '')
    jd = str(job.get('jd') or '')
    text = title + '\n' + stated + '\n' + jd
    if re.search(r'\bintern(?:ship)?\b|实习(?:生|岗位)?', title + '\n' + stated, re.I) or re.search(r'\b(?:this|the) internship (?:role|position|program|programme)\b|实习(?:岗位|职位|项目)', jd, re.I):
        return 'internship'
    if re.search(r'\bgraduate\s+(?:program|programme|scheme)\b|\btrainee\b|\bmanagement\s+trainee\b|管培生|毕业生项目|校招生项目', text, re.I):
        return 'graduate_program'
    if re.search(r'\bfreelance(?:r)?\b|\bproject[- ]based\b|\bindependent contractor\b|项目制|项目合作|自由职业', title + '\n' + stated, re.I):
        return 'project_freelance'
    if re.search(r'\bfull[- ]time\b|\bpermanent\b|\bregular employee\b|全职|正式员工', stated, re.I):
        return 'full_time'
    return 'unknown'


def work_arrangement(job):
    location = str(job.get('location') or '')
    jd = str(job.get('jd') or '')
    location_remote = bool(re.search(r'\bremote\b|远程', location, re.I))
    remote = location_remote or bool(re.search(r'\b(?:fully )?remote (?:role|position|work|working)\b|work remotely|work from home|远程办公', jd, re.I))
    hybrid = bool(re.search(r'\bhybrid\b|混合办公', location + '\n' + jd, re.I))
    onsite = bool(re.search(r'\bon[- ]site\b|\bin[- ]office\b|\boffice[- ]based\b|现场办公|办公室办公', location + '\n' + jd, re.I))
    if hybrid:
        return {'status': 'hybrid', 'label': '混合办公', 'reason': '来源明确写明 hybrid/混合办公。'}
    if remote and onsite:
        return {'status': 'unknown', 'label': '未知', 'reason': '岗位描述同时出现远程与现场信息，需确认实际工作模式。'}
    if remote:
        return {'status': 'remote', 'label': '远程', 'reason': '来源明确写明远程安排；远程雇佣国家仍需单独核实。'}
    if onsite:
        return {'status': 'onsite', 'label': '现场办公', 'reason': '来源明确写明现场办公。'}
    return {'status': 'unknown', 'label': '未知', 'reason': '来源未明确说明工作模式。'}


def compensation_details(job, unpaid=False):
    jd = str(job.get('jd') or '')
    source_value = job.get('compensation')
    lines = [str(line).strip() for line in jd.splitlines() if str(line).strip()]
    pay_lines = [line for line in lines if re.search(r'薪资|薪酬|工资|津贴|补贴|salary|compensation|stipend|pay range|paid internship|unpaid internship|unpaid intern', line, re.I)
                 or re.search(r'(?:CNY|RMB|USD|EUR|GBP|¥|￥)\s*\d|\d+(?:\.\d+)?\s*(?:k|万)\s*(?:-|~|至|–)', line, re.I)]
    if isinstance(source_value, str):
        published = source_value.strip()
    elif isinstance(source_value, (int, float)):
        published = str(source_value)
    elif isinstance(source_value, dict):
        parts = []
        def flatten(value, prefix=''):
            if isinstance(value, dict):
                for key, child in value.items(): flatten(child, (prefix + ' ' + str(key)).strip())
            elif isinstance(value, list):
                for child in value[:6]: flatten(child, prefix)
            elif isinstance(value, (str, int, float)) and str(value).strip():
                parts.append((prefix + ': ' + str(value)).strip(': '))
        flatten(source_value)
        published = ' · '.join(parts)[:240]
    else:
        published = ''
    published = published or (pay_lines[0][:240] if pay_lines else '')
    if unpaid:
        return {'paid_status': 'unpaid', 'published': published or '无薪（来源明确说明）'}
    paid = bool(re.search(r'\bpaid\s+(?:internship|intern|position|role)\b|\b(?:internship|intern)\b.{0,45}\bpaid\b|\b(?:salary|compensation|stipend|pay range)\b|薪资|薪酬|工资|实习津贴|提供薪酬|有薪', jd, re.I))
    if not paid and ((isinstance(source_value, str) and source_value.strip()) or isinstance(source_value, (int, float, dict))):
        paid = True
    return {'paid_status': 'paid' if paid else 'unknown',
            'published': published or '未知（来源未披露）'}


def internship_qualification(job, requirements, source_status, category=None):
    category = category or employment_category(job)
    if category != 'internship':
        return {'status': 'not_applicable', 'reason': '非 Internship 岗位。'}
    if source_status != 'verified_open':
        return {'status': 'needs_confirmation', 'reason': '尚未通过当前官方岗位页面核验资格条件。'}
    text = str(job.get('title') or '') + '\n' + str(job.get('employment_type') or '') + '\n' + str(job.get('jd') or '')
    graduation_rule = re.compile(r'在校|在读|学生|毕业|届|enroll|student|graduate|graduat|class of', re.I)
    mismatches = [item for item in requirements if item.get('level') == 'required'
                  and item.get('status') == 'not_met'
                  and graduation_rule.search(str(item.get('text') or ''))]
    if mismatches:
        return {'status': 'ineligible', 'reason': '官方 JD 的在校/毕业年份条件与已确认的毕业背景冲突：' + '；'.join(item['text'] for item in mismatches),
                'evidence': [item['text'] for item in mismatches]}
    student_only = re.search(r'\bonly\s+(?:current\s+)?(?:university\s+)?students?\b|\bcurrent (?:university )?students? only\b|\bmust be (?:currently )?enrolled\b|\bonly applicants? who are (?:currently )?enrolled\b|仅限在校生|只招在校生|仅限在读学生|在校生专属', text, re.I)
    if student_only:
        return {'status': 'ineligible', 'reason': '官方 JD 明确限定当前在校申请人：' + student_only.group(0),
                'evidence': [student_only.group(0)]}
    recent_only = bool(re.search(r'\b(?:open to|welcome|accept)\s+(?:only\s+)?recent graduates?\b|\brecent graduates?\s+(?:are\s+)?(?:welcome|only)\b|仅限应届毕业生|仅接受应届毕业生', text, re.I))
    explicit_acceptance = bool(re.search(
        r'\b(?:open to|welcome|accept)\s+(?:all\s+)?graduates?\b|\bgraduates?\s+(?:are\s+)?(?:welcome|may apply|can apply|are eligible)\b|\bnon[- ]students?\s+(?:may|can|are welcome to)\s+apply\b|\b(?:no|not)\s+(?:current\s+)?enrol(?:l)?ment\s+(?:is\s+)?required\b|\bcurrent students?\s+and\s+graduates?\b|接受(?:已毕业|往届毕业)人员|已毕业(?:人员)?可申请|毕业生均可申请|毕业生可申请|非在校生(?:也|亦)?可申请|非在读(?:人员)?可申请|不要求(?:当前)?在校|不要求在读', text, re.I))
    if recent_only and not re.search(r'\b(?:within|past|last)\s+3\s+years?\b|近三年|三年内', text, re.I):
        return {'status': 'needs_confirmation', 'reason': '官方仅写“应届/近期毕业生”，未定义年限；需确认是否接受当前候选人的毕业时间。'}
    if explicit_acceptance:
        return {'status': 'eligible', 'reason': '官方 JD 明确接受毕业生或非在校申请人。'}
    return {'status': 'needs_confirmation', 'reason': '官方 JD 未说明是否接受已毕业、非在校人员；需向招聘方确认。'}


def internship_growth(job, category=None):
    if (category or employment_category(job)) != 'internship':
        return {'status': 'not_applicable', 'reason': '非 Internship 岗位。'}
    text = str(job.get('jd') or '')
    signal = re.search(r'\bmentorship\b|\bmentor(?:ing)?\b|\btraining (?:program|programme|provided)\b|\bprofessional development\b|\brotation\b|\bownership\b|\bend[- ]to[- ]end project\b|导师|带教|培训(?:计划|项目)?|轮岗|培养计划|独立负责|项目主导|转正机会', text, re.I)
    return ({'status': 'supported', 'reason': 'JD 明确提到带教、培训、轮岗、项目负责或发展机会：' + signal.group(0)}
            if signal else {'status': 'unknown', 'reason': 'JD 未明确说明成长机制；可询问带教、培训与项目负责范围。'})


def target_alignment(job, preferences):
    strategy = preferences.get('job_search_strategy') if isinstance(preferences, dict) else None
    directions = strategy.get('target_directions', []) if isinstance(strategy, dict) else []
    text = str(job.get('title') or '') + '\n' + str(job.get('jd') or '')
    if isinstance(directions, list) and directions:
        for direction in directions:
            if not isinstance(direction, dict): continue
            keywords = direction.get('keywords', [])
            hit = next((str(keyword) for keyword in keywords if isinstance(keyword, str) and keyword.strip()
                        and re.search(re.escape(keyword.strip()), text, re.I)), None)
            if hit:
                return direction.get('priority'), direction.get('label') or hit, hit
        return None, None, None
    # Compatibility for existing cases that predate per-case target directions.
    if re.search(r'AI\s*(?:operations?|运营)|LLM\s*(?:evaluation|quality)|AI\s*(?:content|data)\s*(?:quality|operations?)|data quality|knowledge operations|知识库运营|大模型评测|AI 质量|AI内容质量|数据质量', text, re.I):
        return 'P0', 'AI / 数据质量运营', 'AI / LLM / Data Operations'
    if re.search(r'product operations? associate|product assistant|AI SaaS customer success|junior digital operations|产品运营专员|产品助理|客户成功|数字化运营', text, re.I):
        return 'P1', '产品运营 / 产品助理', 'Product Operations'
    if re.search(r'UX research assistant|research operations?|associate AI product manager|用户研究助理|研究运营|助理 AI 产品经理', text, re.I):
        return 'P2', 'UX / AI 产品初级岗位', 'UX Research'
    return None, None, None


def matching(case, job):
    from resume_pipeline import load_evidence, route
    error = ''
    try:
        evidence = load_evidence(Path(case))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        error = str(exc)
        evidence = {'person': {}, 'entries': []}
    if not error and not evidence['person'].get('graduation_date'):
        try:
            bank = local_file(case, 'career-evidence-bank.md').read_text(encoding='utf-8')
            dates = []
            for line in bank.splitlines():
                if re.search(r'毕业时间|毕业日期|graduation date', line, re.I):
                    match_date = re.search(r'\b(20\d{2})[.\-/年](0?[1-9]|1[0-2])(?:月)?', line, re.I)
                    if match_date:
                        dates.append(f'{match_date.group(1)}-{int(match_date.group(2)):02d}')
            dates = list(dict.fromkeys(dates))
            if len(dates) == 1:
                evidence['person']['graduation_date'] = dates[0]
                evidence['person']['graduation_source_ref'] = 'career-evidence-bank.md#毕业时间'
        except (OSError, ValueError):
            pass
    requirements = assess(job['jd'], evidence) if job['jd'] else []
    required = [r for r in requirements if r['level'] == 'required']
    blockers = [r for r in required if r['status'] != 'supported']
    pref = read_json(case, 'search-preferences.json', {})
    if not isinstance(pref, dict): pref = {}
    excluded_names = {str(c).strip().casefold() for c in pref.get('excluded_companies', []) if isinstance(c, str)}
    excluded = job['company'].strip().casefold() in excluded_names
    full = sum(3 if r['level'] == 'required' else 1 for r in requirements)
    score = None if error or not full else round(100 * sum((3 if r['level'] == 'required' else 1) for r in requirements if r['status'] == 'supported') / full)
    flags = []
    hard_reasons = []
    jd = job['jd']
    if re.search(r'人才库|talent (?:pool|network|community)|join our database', jd, re.I):
        flags.append('仅人才库登记，未证明存在具体职位与即时招聘名额。')
        hard_reasons.append('不是可核验的具体空缺岗位。')
    unpaid = bool(re.search(r'\bunpaid\s+(?:internship|intern|position|role|job|opportunity)\b|\b(?:internship|intern|position|role|job)\b.{0,45}\bunpaid\b|without pay|uncompensated internship|unpaid\s+work|无薪实习|无薪岗位|不提供薪资', jd, re.I))
    if unpaid:
        flags.append('JD 明确无薪；薪资低于偏好，默认降级，是否破例由本人决定。')
    remote = bool(re.search(r'\bremote\b|远程', job['location'] + ' ' + str(job['employment_type']) + ' ' + jd, re.I))
    china_location = bool(re.search(r'Shanghai|Suzhou|上海|苏州|\bChina\b|中国', job['location'], re.I))
    preferred_city = bool(re.search(r'Shanghai|Suzhou|上海|苏州', job['location'], re.I))
    china_remote = remote and bool(re.search(r'\bChina\b|中国', job['location'] + ' ' + jd, re.I))
    if remote:
        flags.append('需确认远程雇佣国家、合同主体及对应工作许可。')
    if not china_location:
        flags.append('地点尚未证明符合上海、苏州或中国远程范围。')
    elif not preferred_city and not china_remote:
        flags.append('地点在中国但不属于当前优先的上海、苏州或中国远程。')
    if excluded:
        hard_reasons.append('企业命中本人屏蔽名单。')

    # Keep the historical preference verbatim. Its currency/period are not
    # structured, so it cannot silently make an unpublished or foreign salary pass.
    salary_floor = pref.get('salary_floor') if isinstance(pref.get('salary_floor'), dict) else None
    salary_text = ''
    try:
        bank = local_file(case, 'career-evidence-bank.md').read_text(encoding='utf-8')
        found = re.search(r'期望薪资\s*[：:]\s*([^\n；;]+)', bank)
        salary_text = found.group(1).strip() if found else ''
    except OSError:
        pass
    salary = {'status': 'unknown', 'floor_text': salary_text or '未知',
              'floor_source_ref': 'career-evidence-bank.md#期望薪资' if salary_text else '',
              'reason': 'JD 未提供可比较的明确薪资；不默认符合既有底线。'}
    salary_match = re.search(r'(?:CNY|RMB|人民币|¥|￥)\s*(\d+(?:\.\d+)?)\s*(k|万)?\s*(?:-|~|至|–)\s*(\d+(?:\.\d+)?)\s*(k|万)?\s*(?:CNY|RMB|人民币|元)?\s*(?:/\s*月|每月|月薪)', jd, re.I)
    if salary_match and salary_floor and salary_floor.get('currency') == 'CNY' and salary_floor.get('period') == 'month':
        def monthly_amount(value, unit):
            return float(value) * (1000 if (unit or '').lower() == 'k' else 10000 if unit == '万' else 1)
        lower = monthly_amount(salary_match.group(1), salary_match.group(2))
        floor_amount = salary_floor.get('amount')
        if isinstance(floor_amount, (int, float)):
            salary['status'] = 'supported' if lower >= floor_amount else 'not_met'
            salary['reason'] = '已按明确标注的人民币月薪与结构化个人底线比较。'
            salary['observed_min_cny_month'] = lower
            if salary['status'] == 'not_met': hard_reasons.append('明确月薪低于已确认的个人薪资底线。')
    elif salary_match:
        salary['status'] = 'unknown'
        salary['reason'] = 'JD 有月薪信息，但既有底线的币种或周期未结构化；需要本人确认比较口径。'
    elif re.search(r'薪资|薪酬|工资|salary|compensation|\b\d+(?:\.\d+)?\s*(?:k|万)\b', jd, re.I):
        salary['reason'] = 'JD 提及薪资，但没有可可靠换算的币种、周期或范围。'

    verification = job.get('verification', {})
    source_status = verification.get('status', 'unknown')
    category = employment_category(job)
    work_mode = work_arrangement(job)
    compensation = compensation_details(job, unpaid=unpaid)
    internship_status = internship_qualification(job, requirements, source_status, category)
    growth = internship_growth(job, category)
    strategy = pref.get('job_search_strategy') if isinstance(pref.get('job_search_strategy'), dict) else {}
    if category == 'internship':
        inquiry_context = strategy.get('graduation_context_for_inquiry')
        internship_status['inquiry_context'] = str(inquiry_context)[:100] if isinstance(inquiry_context, str) and inquiry_context.strip() else '已完成本科学业（毕业年限可补充）'
    if internship_status['status'] == 'ineligible':
        hard_reasons.append(internship_status['reason'])
    elif internship_status['status'] == 'needs_confirmation':
        flags.append(internship_status['reason'])
    if category == 'internship' and growth['status'] == 'unknown':
        flags.append(growth['reason'])
    if compensation['paid_status'] == 'unknown':
        flags.append('薪资/有薪状态未能从官方来源确认；按既有薪资偏好待核实。')
    if source_status == 'closed': hard_reasons.append('官方来源明确显示岗位已关闭或不可申请。')
    elif source_status != 'verified_open': flags.append('官方当前可申请状态未能核验。')
    if not requirements: flags.append('JD 中未识别到足够的资格要求，需人工审阅完整原文。')
    if error: flags.append('当前事实缓存来源待复核，暂不使用过期个人事实。')
    if any(r['status'] == 'not_met' for r in blockers):
        hard_reasons.extend('硬条件不满足：' + r['text'] for r in blockers if r['status'] == 'not_met')
    if any(r['status'] in {'unknown', 'partial'} for r in blockers):
        flags.extend('硬条件待核实：' + r['text'] for r in blockers if r['status'] in {'unknown', 'partial'})

    direct_refs = list(dict.fromkeys(ref for item in requirements for ref in item.get('evidence_refs', [])))
    evidence_kinds = {proof.get('kind') for item in requirements for proof in item.get('evidence', [])}
    evidence_by_kind = {kind: list(dict.fromkeys(
        proof['id'] for item in requirements for proof in item.get('evidence', []) if proof.get('kind') == kind
    )) for kind in ('work', 'project', 'education', 'profile')}
    target_priority, target_label, target_keyword = target_alignment(job, pref)
    if target_priority:
        flags.append('命中个人目标方向 ' + str(target_priority) + '：' + str(target_label) + '（依据：' + str(target_keyword) + '）。')
    if direct_refs:
        flags.append('已找到岗位要求相关的可追溯个人事实，具体证据须逐条人工复核。')
    else:
        flags.append('目前没有足够的直接个人事实覆盖岗位要求。')

    grade_reasons = []
    if excluded or source_status == 'closed' or internship_status['status'] == 'ineligible' or any(r['status'] == 'not_met' for r in blockers) or salary['status'] == 'not_met':
        grade = 'D'
        grade_reasons.extend(hard_reasons)
    elif source_status != 'verified_open' or not job.get('url') or not job.get('jd'):
        grade = 'U'
        grade_reasons.append('无法用当前官方来源证明这是仍可申请的具体岗位。')
    elif unpaid:
        grade = 'C'
        grade_reasons.extend(flags)
    elif error or blockers or remote or not china_location or salary['status'] != 'supported' or internship_status['status'] == 'needs_confirmation' or (category == 'internship' and growth['status'] != 'supported'):
        grade = 'B'
        grade_reasons.extend(flags)
    elif (not preferred_city and not china_remote) or target_priority is None or not direct_refs or not evidence_kinds.intersection({'work', 'project'}):
        grade = 'C'
        grade_reasons.append('岗位硬条件已核验，但地点、目标方向或真实工作/项目证据关联不足。')
    else:
        grade = 'A'
        grade_reasons.append('官方状态、主要硬条件、工作地点与薪资底线均有当前证据支持；仍需本人审核申请材料。')
    return dict(grade=grade, grade_reasons=list(dict.fromkeys(grade_reasons)),
                requirements=requirements, score=score, score_label=SCORE_LABEL,
                priority={'A': 'apply_review', 'B': 'verify_first', 'C': 'hold', 'D': 'exclude', 'U': 'unverified'}[grade],
                warnings=list(dict.fromkeys(flags)), hard_reasons=list(dict.fromkeys(hard_reasons)), salary=salary,
                target_priority=target_priority, target_label=target_label,
                employment_category=category, internship_qualification=internship_status,
                internship_growth=growth, work_mode=work_mode, posted_compensation=compensation,
                evidence_by_kind=evidence_by_kind,
                evidence_refs=direct_refs, evidence_error=error, routing=route(jd, job['title']),
                eligibility='not_met' if grade == 'D' else 'needs_review', rules_version=MATCH_RULES_VERSION,
                assessed_at=records.now(), ready_to_apply=False)


def same_job(case, job):
    target = records.canonical(job['url'])
    for path, item in records.manifests(Path(case)):
        same_id = job.get('requisition_id') and job.get('employer_namespace') == item.get('employer_namespace') and job['requisition_id'] == item.get('requisition_id')
        if same_id or any(records.canonical(u) == target for u in [item['url']] + item.get('aliases', [])):
            return path, item
    for item in records.rows(Path(case))[0]:
        if item.get('url') and records.canonical(item['url']) == target:
            return None, item
    return None, None


def _store_observation(case, key, job):
    """Save each official response as an immutable local snapshot."""
    raw = job.pop('_body')
    digest = hashlib.sha256(raw.encode()).hexdigest()
    folder = local_file(case, 'applications/' + key)
    snapshots = folder / 'official-sources'
    snapshots.mkdir(parents=True, exist_ok=True)
    stamp = re.sub(r'[^0-9TZ+-]', '-', job['verification']['checked_at'])
    relative = f'applications/{key}/official-sources/{stamp}-{digest[:12]}.txt'
    target = local_file(case, relative)
    if not target.exists():
        records.atomic(target, raw)
    job['verification']['content_sha256'] = digest
    job['verification']['source_path'] = relative
    return raw


def _restore_tracker_from_manifest(case, manifest):
    """Repair a missing summary row from its existing manifest; do not alter history."""
    rows, fields = records.rows(case)
    if any(row.get('job_key') == manifest.get('job_key') for row in rows):
        return False
    key = manifest.get('job_key')
    if not isinstance(key, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,119}', key):
        return False
    status = manifest.get('status')
    if status not in records.STAGES:
        return False
    manifest_url = manifest.get('url', '')
    namespace, requisition_id = manifest.get('employer_namespace'), manifest.get('requisition_id')
    for row in rows:
        if row.get('job_key') == key:
            continue
        if namespace and requisition_id and (row.get('employer_namespace'), row.get('requisition_id')) == (namespace, requisition_id):
            return False
        if row.get('url'):
            try:
                if records.canonical(row['url']) == records.canonical(manifest_url):
                    return False
            except ValueError:
                return False
    row = {field: manifest.get(field, '') for field in records.FIELDS}
    row['job_key'] = key
    row['status'] = status
    row['execution_status'] = manifest.get('execution_status') or 'idle'
    row['sync_status'] = manifest.get('sync_status') or 'not_requested'
    row['updated_at'] = records.now()
    rows.append(row)
    records.save_rows(case, rows, fields)
    return True


def import_url(case, request, transport=None):
    if not isinstance(request, dict) or set(request) != {'url'}:
        raise ValueError('仅接受 url；已核验状态只能由服务端实际读取产生')
    case = Path(case).resolve()
    job = observe(request['url'], transport)
    with records.lock(case):
        path, existing = same_job(case, job)
        if existing:
            key = existing['job_key']
            manifest = existing
            restored = False
            if path is not None:
                restored = _restore_tracker_from_manifest(case, manifest)
            # A duplicate is still a fresh observation. Append a new source snapshot
            # and refresh only the discovery record; preserve manifests, resume files,
            # stage, receipts, and the event journal.
            if path is not None and manifest.get('opportunity_path'):
                prior_path = local_file(case, manifest['opportunity_path'])
                prior = read_json(case, manifest['opportunity_path'], {}) if prior_path.is_file() else {}
                _store_observation(case, key, job)
                job['job_key'] = key
                job['match'] = matching(case, job)
                observations = prior.get('observations', []) if isinstance(prior.get('observations', []), list) else []
                observations.append({k: job['verification'].get(k) for k in ('checked_at', 'status', 'source_url', 'source_path', 'content_sha256', 'reason')})
                job['observations'] = observations[-50:]
                records.atomic(prior_path, json.dumps(job, ensure_ascii=False, indent=2))
            else:
                job['_body'] = ''
            tracker_row = next((row for row in records.rows(case)[0] if row.get('job_key') == key), None)
            return {'job_key': key, 'duplicate': True,
                    'status': tracker_row.get('status') if tracker_row else existing.get('status', 'discovered'),
                    'refreshed': path is not None and bool(manifest.get('opportunity_path')),
                    'tracker_restored': restored,
                    'note': '岗位已去重；仅追加官网观察快照，原申请阶段、回执、材料和事件保持不变'}
        identity = job['employer_namespace'] + ':' + (job['requisition_id'] or records.canonical(job['url']))
        key = 'opportunity-' + hashlib.sha256(identity.encode()).hexdigest()[:20]
        folder = local_file(case, 'applications/' + key)
        folder.mkdir(parents=True, exist_ok=True)
        raw = _store_observation(case, key, job)
        records.atomic(folder / 'official-source.txt', raw)
        records.atomic(folder / 'jd.md', '# ' + job['title'] + '\n\n来源：' + job['url'] + '\n\n' + (job['jd'] or '官网 JD 未读取成功；不得用于简历生成。'))
        job['match'] = matching(case, job)
        job['job_key'] = key
        job['observations'] = [{k: job['verification'].get(k) for k in ('checked_at', 'status', 'source_url', 'source_path', 'content_sha256', 'reason')}]
        records.atomic(folder / 'opportunity.json', json.dumps(job, ensure_ascii=False, indent=2))
        manifest = dict(job_key=key, company=job['company'], role=job['title'], url=job['url'], location=job['location'],
                        employer_namespace=job['employer_namespace'], requisition_id=job['requisition_id'],
                        status='discovered', execution_status='idle', sync_status='not_requested',
                        jd_path=f'applications/{key}/jd.md', evidence_refs=[],
                        opportunity_path=f'applications/{key}/opportunity.json', authorization_scope='',
                        next_action='核对官网有效性、资格和证据；未投递', updated_at=records.now())
        records.validate(case, manifest); records.duplicate(case, manifest)
        records.atomic(folder / 'manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        records.upsert(case, manifest)
        return {'job_key': key, 'duplicate': False, 'status': 'discovered', 'job': job}


def list_jobs(case):
    result = []
    for _, manifest in records.manifests(Path(case)):
        if not manifest.get('opportunity_path'): continue
        job = read_json(case, manifest['opportunity_path'], {})
        job['job_key'] = manifest['job_key']
        v = job.get('verification', {})
        try:
            source_path = v.get('source_path') or f"applications/{manifest['job_key']}/official-source.txt"
            proof = local_file(case, source_path)
        except (ValueError, OSError):
            proof = None
        if proof is None or not proof.is_file() or records.digest(proof) != v.get('content_sha256'):
            v.update(status='unknown', verified_at=None, reason='来源快照缺失或已变化')
        elif v.get('verified_at'):
            if datetime.now(timezone.utc) - records.stamp(v['verified_at']) > timedelta(hours=24):
                v.update(status='stale', reason='核验已超过 24 小时；再次使用前需刷新')
        job['match'] = matching(case, job)
        result.append(job)
    return {'jobs': result, 'score_label': SCORE_LABEL, 'mode': 'discovery-only'}


def studio_job(case, key):
    if not isinstance(key, str) or not re.fullmatch(r'opportunity-[a-f0-9]{20}', key):
        raise ValueError('无效的岗位编号')
    job = next((j for j in list_jobs(case)['jobs'] if j['job_key'] == key), None)
    if not job or len(job.get('jd', '')) < 40:
        raise ValueError('未读取到完整 JD；请先核实官网或手动粘贴正文')
    return {k: job[k] for k in ('jd', 'title', 'company', 'url')}


def discover(case, tenant, limit=10, transport=None):
    """Public Lever feed; deliberate bounded scan, no background scheduler."""
    if tenant not in LEVER or type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError('请选择支持的 ATS 租户，每轮最多 10 个岗位')
    get = transport or fetch
    code, final, body = get(f'https://api.lever.co/v0/postings/{tenant}?mode=json')
    if code != 200 or final != f'https://api.lever.co/v0/postings/{tenant}?mode=json':
        raise ValueError('官方职位列表读取失败')
    jobs = json.loads(body)
    if not isinstance(jobs, list): raise ValueError('官方职位列表格式有误')
    patterns = r'AI|LLM|evaluation|content|data|product|research|评测|产品|内容'
    pref = read_json(case, 'search-preferences.json', {})
    excluded = {str(c).casefold() for c in pref.get('excluded_companies', [])}
    candidates = [j for j in jobs if isinstance(j, dict) and re.search(patterns, j.get('text', ''), re.I)
                  and re.search(r'China|Shanghai|Suzhou|上海|苏州|中国', j.get('categories', {}).get('location', ''), re.I)
                  and LEVER[tenant].casefold() not in excluded
                  and not re.search(r'senior|director|head of|高级|总监', j.get('text', ''), re.I)]
    # Import performs a second live read, not a verification of feed snippets.
    return {'results': [import_url(case, {'url': j['hostedUrl']}, get) for j in candidates[:limit]],
            'mode': 'discovery-only', 'note': '仅按已支持的公开 ATS 列表检索；未覆盖全部外企官网'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--url'); group.add_argument('--discover', choices=list(LEVER)); group.add_argument('--list', action='store_true')
    args = parser.parse_args()
    result = import_url(args.case, {'url': args.url}) if args.url else discover(args.case, args.discover) if args.discover else list_jobs(args.case)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
