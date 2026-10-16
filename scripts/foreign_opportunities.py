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
                    adapter='html', fetch_url=url)
    if host in {'jobs.sap.com', 'careers.sap.com'} and ('/job/' in path or re.match(r'/en/jobs/\d+/', path)):
        return dict(company='SAP', namespace='sap', requisition_id='', adapter='html', fetch_url=url)
    if host == 'jobs.ikea.com' and path.startswith('/en/job/'):
        return dict(company='IKEA', namespace='ikea', requisition_id='', adapter='html', fetch_url=url)
    raise ValueError('尚未支持此官方域名或 ATS 租户；可在 JD Studio 手动分析，不能标记已核验')


def network_url(url):
    p = urlsplit(url)
    hosts = {'api.lever.co', 'jobs.smartrecruiters.com', 'jobs.sap.com', 'careers.sap.com', 'jobs.ikea.com', *WORKDAY}
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
                   apply_url=data.get('applyUrl', ''))
        row['jd'] = '\n'.join([data.get('descriptionPlain', '')] +
                             [item.get('text', '') + '\n' + plain(item.get('content', '')) for item in data.get('lists', [])] +
                             [data.get('additionalPlain', '')]).replace('\\n', '\n').strip()
        row['accepting'] = bool(row['title'] and row['jd'] and row['apply_url'])
    elif origin['adapter'] == 'workday':
        data = json.loads(body).get('jobPostingInfo', {})
        row.update(title=data.get('title', ''), jd=plain(data.get('jobDescription', '')),
                   requisition_id=data.get('jobReqId', ''), location=data.get('location', '未知'),
                   employment_type=data.get('timeType', '未知'), posted_date_text=data.get('postedOn', '未知'))
        posted = data.get('startDate', '')
        row['posted_date'] = posted if re.fullmatch(r'\d{4}-\d{2}-\d{2}', posted) else None
        row['accepting'] = data.get('canApply') is True
        row['apply_url'] = url if row['accepting'] else ''
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
                       employment_type=data.get('employmentType', '未知'))
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
            verification['status'] = 'verified_open' if len(row['jd']) >= 40 and row['title'] and row['accepting'] else 'closed' if row.get('expired') else 'unknown'
            if verification['status'] == 'verified_open': verification['verified_at'] = checked
    except HTTPError as error:
        verification.update(http_status=error.code, status='closed' if error.code in {404, 410} else 'unknown', reason='官方页面返回 HTTP ' + str(error.code))
    except (ValueError, OSError, URLError, KeyError, TypeError) as error:
        verification['reason'] = '读取未完成：' + type(error).__name__
    verification['content_sha256'] = hashlib.sha256(body.encode()).hexdigest()
    row['verification'] = verification
    row['_body'] = body
    return row


def matching(case, job):
    from resume_pipeline import load_evidence, route
    error = ''
    try:
        evidence = load_evidence(Path(case))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        error = str(exc)
        evidence = {'person': {}, 'entries': []}
    requirements = assess(job['jd'], evidence) if job['jd'] else []
    blockers = [r for r in requirements if r['level'] == 'required' and r['status'] != 'supported']
    pref = read_json(case, 'search-preferences.json', {})
    excluded = job['company'].casefold() in {str(c).casefold() for c in pref.get('excluded_companies', [])}
    full = sum(3 if r['level'] == 'required' else 1 for r in requirements)
    score = None if error or not full else round(100 * sum((3 if r['level'] == 'required' else 1) for r in requirements if r['status'] == 'supported') / full)
    flags = []
    jd = job['jd']
    if re.search(r'人才库|talent (?:pool|network|community)|join our database', jd, re.I): flags.append('人才库机会；不保证存在即时项目或雇佣名额')
    if re.search(r'\bunpaid\b|无薪', jd, re.I): flags.append('无薪机会；不默认符合薪资偏好')
    if re.search(r'\bremote\b|远程', job['location'] + ' ' + str(job['employment_type']) + ' ' + jd, re.I): flags.append('远程雇佣国家、合同主体及工作许可需单独核实')
    if not re.search(r'Shanghai|Suzhou|上海|苏州|\bChina\b|中国', job['location'], re.I): flags.append('地点未证明符合上海、苏州或中国远程范围')
    priority = 'exclude' if excluded or any(r['status'] == 'not_met' for r in blockers) or job['verification']['status'] == 'closed' else 'verify_first' if error or blockers or flags or job['verification']['status'] != 'verified_open' or not requirements else 'review_first'
    return dict(requirements=requirements, score=score, score_label=SCORE_LABEL, priority=priority,
                warnings=flags, evidence_error=error, routing=route(jd, job['title']),
                eligibility='not_met' if priority == 'exclude' else 'needs_review', ready_to_apply=False)


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


def import_url(case, request, transport=None):
    if not isinstance(request, dict) or set(request) != {'url'}:
        raise ValueError('仅接受 url；已核验状态只能由服务端实际读取产生')
    case = Path(case).resolve()
    job = observe(request['url'], transport)
    with records.lock(case):
        path, existing = same_job(case, job)
        if existing:
            return {'job_key': existing['job_key'], 'duplicate': True, 'status': existing['status'], 'note': '已有同一岗位，未覆盖材料、历史或阶段'}
        identity = job['employer_namespace'] + ':' + (job['requisition_id'] or records.canonical(job['url']))
        key = 'opportunity-' + hashlib.sha256(identity.encode()).hexdigest()[:20]
        folder = local_file(case, 'applications/' + key)
        folder.mkdir(parents=True, exist_ok=True)
        raw = job.pop('_body')
        records.atomic(folder / 'official-source.txt', raw)
        records.atomic(folder / 'jd.md', '# ' + job['title'] + '\n\n来源：' + job['url'] + '\n\n' + (job['jd'] or '官网 JD 未读取成功；不得用于简历生成。'))
        job['match'] = matching(case, job)
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
        proof = local_file(case, f"applications/{manifest['job_key']}/official-source.txt")
        v = job.get('verification', {})
        if not proof.is_file() or records.digest(proof) != v.get('content_sha256'):
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
