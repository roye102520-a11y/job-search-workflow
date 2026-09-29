"""Offline BOSS job-list assistant. No scraping, browser actions, or messages.

The caller supplies a JSON/CSV export and explicit preferences. Results are
review notes, never evidence that a vacancy is live or an application was sent.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import string
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit


FIELDS = {
    'url': ('url', 'link', 'job_url', '岗位链接', '职位链接', '链接'),
    'company': ('company', 'company_name', '公司', '公司名称'),
    'title': ('title', 'job_title', 'position', '岗位', '职位', '岗位名称', '职位名称'),
    'city': ('city', 'location', '城市', '工作地点'),
    'salary': ('salary', 'salary_range', '薪资', '薪资范围'),
    'company_size': ('company_size', 'company_scale', '公司规模', '规模'),
    'open_positions': ('open_positions', 'open_jobs', '在招岗位数', '在招数'),
    'tags': ('tags', 'labels', '标签'),
    'description': ('description', 'summary', 'intro', '简介', '岗位简介'),
}
CONFIG_KEYS = {
    'keywords', 'cities', 'min_salary_k', 'max_salary_k', 'company_sizes',
    'excluded_companies', 'require_weekends_off', 'max_open_positions',
    'greeting_template', 'greeting_confirmed',
}
DEFAULT_CONFIG = {
    'keywords': [], 'cities': [], 'min_salary_k': None, 'max_salary_k': None,
    'company_sizes': [], 'excluded_companies': [],
    'require_weekends_off': False, 'max_open_positions': 0,
    'greeting_template': '', 'greeting_confirmed': False,
}
_BOSS_HOSTS = {'zhipin.com', 'www.zhipin.com', 'm.zhipin.com'}
_DETAIL_PATH = re.compile(r'^/job_detail/([A-Za-z0-9]{8,64})\.html/?$')
_WEEKEND_NEGATIVE = re.compile(r'无双休|不(?:是|保证|提供|支持)?双休|非双休|单休|大小周|单双休')


def _clean(value: object) -> str:
    if value is None:
        return ''
    if isinstance(value, (dict, list)):
        if isinstance(value, list) and all(isinstance(item, (str, int, float)) for item in value):
            return ' '.join(str(item).strip() for item in value)
        raise ValueError('岗位字段应为文字或简单标签列表')
    if isinstance(value, bool):
        raise ValueError('岗位字段不能为布尔值')
    return str(value).strip()


def _key(value: str) -> str:
    return ''.join(unicodedata.normalize('NFKC', value).casefold().split())


def _string_list(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError(f'{name} 必须是最多 100 项的文字列表')
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 100 or any(ord(ch) < 32 for ch in item):
            raise ValueError(f'{name} 含无效项目')
        if _key(item) not in {_key(existing) for existing in result}:
            result.append(item.strip())
    return result


def validate_config(config: dict) -> dict:
    """Validate and normalize user choices; reject typos instead of ignoring them."""
    if not isinstance(config, dict) or set(config) - CONFIG_KEYS:
        raise ValueError('筛选设置格式错误或包含未知字段')
    clean = {**DEFAULT_CONFIG, **config}
    for field in ('keywords', 'cities', 'company_sizes', 'excluded_companies'):
        clean[field] = _string_list(clean[field], field)
    for field in ('min_salary_k', 'max_salary_k'):
        value = clean[field]
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0 or value > 1000):
            raise ValueError(f'{field} 应为正数 K/月或 null')
    if clean['min_salary_k'] is not None and clean['max_salary_k'] is not None and clean['min_salary_k'] > clean['max_salary_k']:
        raise ValueError('最低薪资不能高于最高薪资')
    value = clean['max_open_positions']
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError('max_open_positions 必须是非负整数；0 表示不限')
    for field in ('require_weekends_off', 'greeting_confirmed'):
        if not isinstance(clean[field], bool):
            raise ValueError(f'{field} 必须为布尔值')
    template = clean['greeting_template']
    if not isinstance(template, str) or len(template) > 400 or any(ord(ch) < 32 and ch != '\n' for ch in template):
        raise ValueError('招呼语模板必须是 400 字以内的文字')
    try:
        placeholders = list(string.Formatter().parse(template))
    except ValueError as exc:
        raise ValueError('招呼语模板的大括号格式错误') from exc
    if any(field not in (None, 'company', 'title') or spec or conversion for _, field, spec, conversion in placeholders):
        raise ValueError('招呼语模板只允许 {company}、{title} 两个占位符')
    if clean['greeting_confirmed'] and not template.strip():
        raise ValueError('确认招呼语前必须提供模板')
    return clean


def import_blocked_companies(text: str) -> list[str]:
    """Import pasted names, a JSON array, or a CSV with a company column."""
    if not isinstance(text, str):
        raise ValueError('屏蔽公司内容必须是文字')
    raw = text.lstrip('\ufeff\n\r\t ')
    if raw.startswith(('[', '{')):
        payload = json.loads(raw)
        if isinstance(payload, dict):
            payload = payload.get('blocked_companies', payload.get('companies'))
        if not isinstance(payload, list):
            raise ValueError('屏蔽公司 JSON 应为名称数组或包含 blocked_companies 的对象')
        parts = []
        for item in payload:
            if isinstance(item, dict):
                item = item.get('company', item.get('name'))
            if not isinstance(item, str):
                raise ValueError('屏蔽公司 JSON 项应为公司名称文字')
            parts.append(item)
    else:
        first_line = raw.splitlines()[0] if raw else ''
        header = next(csv.reader([first_line]), [])
        company_column = next((name for name in header if name.strip().casefold() in
                               {'公司', '公司名称', 'company', 'company_name', 'blocked_company'}), None)
        if company_column and len(header) > 1:
            parts = [row.get(company_column, '') for row in csv.DictReader(io.StringIO(raw, newline=''))]
        else:
            parts = re.split(r'[\n,，;；]+', raw)
    names = []
    for part in parts:
        if not isinstance(part, str):
            raise ValueError('屏蔽公司名称应为文字')
        name = re.sub(r'^\s*(?:[-*•]|\d+[.)、])\s*', '', part).strip()
        if not name or name.startswith('#') or name in {'公司', '公司名称', '屏蔽公司'}:
            continue
        if len(name) > 100 or any(ord(ch) < 32 for ch in name):
            raise ValueError('屏蔽公司名称无效')
        if _key(name) not in {_key(existing) for existing in names}:
            names.append(name)
    return names


def parse_jobs_text(text: str, format_hint: str | None = None) -> list[dict]:
    """Parse pasted JSON or CSV exports. A leading '['/'{' selects JSON by default."""
    if not isinstance(text, str) or len(text.encode('utf-8')) > 10_000_000:
        raise ValueError('岗位导出文字必须为 10 MB 以内的文本')
    raw = text.lstrip('\ufeff\n\r\t ')
    if format_hint not in (None, 'json', 'csv'):
        raise ValueError('format_hint 只支持 json 或 csv')
    kind = format_hint or ('json' if raw.startswith(('[', '{')) else 'csv')
    if kind == 'json':
        payload = json.loads(raw)
        rows = payload.get('jobs') if isinstance(payload, dict) else payload
    else:
        rows = list(csv.DictReader(io.StringIO(raw, newline='')))
    if not isinstance(rows, list) or len(rows) > 5000 or any(not isinstance(row, dict) for row in rows):
        raise ValueError('岗位导出应包含最多 5000 条对象记录')
    if kind == 'csv' and rows and (any(None in row for row in rows) or not any(alias in rows[0] for alias in FIELDS['url'])):
        raise ValueError('CSV 缺少岗位链接表头，或某行列数超过表头')
    return rows


def load_jobs(path: str | Path) -> list[dict]:
    """Read local UTF-8 JSON array/{jobs: [...]} or CSV; no network access."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 10_000_000:
        raise ValueError('岗位导出文件不存在或超过 10 MB')
    kind = path.suffix.lower().lstrip('.')
    if kind not in ('json', 'csv'):
        raise ValueError('仅支持 JSON 或 CSV 岗位导出')
    return parse_jobs_text(path.read_text(encoding='utf-8-sig'), kind)


def _field(row: dict, name: str) -> str:
    for alias in FIELDS[name]:
        if alias in row:
            return _clean(row[alias])
    return ''


def _normalize_job(row: dict) -> dict:
    if not isinstance(row, dict):
        raise ValueError('岗位记录必须是对象')
    job = {name: _field(row, name) for name in FIELDS}
    for field in ('url', 'company', 'title'):
        if not job[field]:
            raise ValueError(f'缺少必填字段：{field}')
    if len(job['company']) > 200 or len(job['title']) > 200 or len(job['url']) > 2000:
        raise ValueError('公司、岗位或链接过长')
    if len(job['description']) > 100000 or len(job['tags']) > 2000 or any(
            len(job[field]) > 500 for field in ('city', 'salary', 'company_size', 'open_positions')):
        raise ValueError('岗位描述或筛选字段过长')
    if any(ord(ch) < 32 for field in ('company', 'title', 'url') for ch in job[field]):
        raise ValueError('公司、岗位或链接含控制字符')
    parsed = urlsplit(job['url'])
    if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('岗位链接必须是有效的 HTTP(S) URL')
    stable_id = stable_boss_id(job['url'])
    if stable_id:
        # BOSS export URLs often include lid/securityId session parameters.
        # The detail path alone supplies the stable identity used here.
        job['url'] = f'https://www.zhipin.com/job_detail/{stable_id}.html'
    return job


def stable_boss_id(url: str) -> str | None:
    """Only a known BOSS job-detail URL has a safe stable deduplication key."""
    try:
        parts = urlsplit(url)
        if (parts.scheme != 'https' or parts.hostname not in _BOSS_HOSTS
                or parts.username or parts.password or parts.port not in (None, 443)):
            return None
        match = _DETAIL_PATH.fullmatch(parts.path)
        return match.group(1) if match else None
    except ValueError:
        return None


def _salary_range_k(value: str) -> tuple[float | None, float | None]:
    """Conservatively parse monthly salary only. Annual/negotiable stays unknown."""
    text = unicodedata.normalize('NFKC', value).replace(' ', '').lower()
    if not text or any(term in text for term in ('面议', '年薪', '/年', '万/年')):
        return None, None
    text = re.split(r'[·•]', text, maxsplit=1)[0]
    match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*[-~～]\s*(\d+(?:\.\d+)?)(k|千|万|元)(?:/月|月)?', text)
    if not match:
        match = re.fullmatch(r'(\d+(?:\.\d+)?)(k|千|万|元)\s*[-~～]\s*(\d+(?:\.\d+)?)(k|千|万|元)(?:/月|月)?', text)
        if not match or match.group(2) != match.group(4):
            return None, None
        low, high, unit = float(match.group(1)), float(match.group(3)), match.group(2)
    else:
        low, high, unit = float(match.group(1)), float(match.group(2)), match.group(3)
    factor = {'k': 1, '千': 1, '万': 10, '元': .001}[unit]
    if low <= 0 or high < low:
        return None, None
    return low * factor, high * factor


def _open_count(value: str) -> int | None:
    text = unicodedata.normalize('NFKC', value).strip()
    match = re.fullmatch(r'(\d+)(?:个|条|个岗位|条岗位)?', text)
    return int(match.group(1)) if match else None


def _weekends(text: str) -> str:
    compact = re.sub(r'\s+', '', text)
    if _WEEKEND_NEGATIVE.search(compact):
        return 'negative'
    return 'stated' if '双休' in compact else 'unknown'


def draft_greeting(job: dict, config: dict) -> str | None:
    """Render a confirmed user template as a draft; never send it."""
    clean = validate_config(config)
    if not clean['greeting_confirmed']:
        return None
    return clean['greeting_template'].format(company=job['company'], title=job['title'])


def evaluate_jobs(rows: list[dict], config: dict) -> dict:
    """Classify imported jobs for human review, preserving every row and reason."""
    clean = validate_config(config)
    if not isinstance(rows, list) or len(rows) > 5000:
        raise ValueError('岗位列表必须是最多 5000 项的数组')
    results, errors, seen = [], [], {}
    for index, row in enumerate(rows, 1):
        try:
            job = _normalize_job(row)
        except (TypeError, ValueError) as exc:
            errors.append({'index': index, 'error': str(exc)})
            continue
        reasons, checks, exclusions = [], [], []
        stable_id = stable_boss_id(job['url'])
        duplicate_of = seen.get(stable_id) if stable_id else None
        if stable_id and duplicate_of is None:
            seen[stable_id] = (index, job['company'], job['title'])
        if duplicate_of:
            original_index, company, title = duplicate_of
            if _key(company) == _key(job['company']) and _key(title) == _key(job['title']):
                status = 'duplicate'
                reasons.append(f'与第 {original_index} 条的 BOSS 岗位详情 ID 相同；已去重。')
            else:
                status = 'needs_verification'
                checks.append(f'与第 {original_index} 条具有同一 BOSS 岗位 ID，但公司或岗位名称冲突；需人工核实。')
            results.append({'index': index, 'job': job, 'stable_job_id': stable_id,
                            'duplicate_of': original_index, 'status': status,
                            'reasons': reasons, 'needs_verification': checks,
                            'greeting_draft': None})
            continue
        if stable_id is None:
            checks.append('链接不是已识别的 BOSS 岗位详情 URL，需核实来源与岗位 ID；未据公司和岗位名合并。')
        else:
            reasons.append('识别到 BOSS 岗位详情 URL 结构；职位在线有效性仍需核实。')
        company_key = _key(job['company'])
        if company_key in {_key(name) for name in clean['excluded_companies']}:
            exclusions.append('公司在用户提供的屏蔽名单中。')
        searchable = ' '.join(job[field] for field in ('title', 'tags', 'description')).casefold()
        if clean['keywords']:
            hits = [word for word in clean['keywords'] if word.casefold() in searchable]
            if hits:
                reasons.append('命中岗位关键词：' + '、'.join(hits))
            else:
                exclusions.append('岗位文字未命中设置的关键词。')
        if clean['cities']:
            if not job['city']:
                checks.append('工作城市未提供，需核实。')
            elif any(_key(city) in _key(job['city']) for city in clean['cities']):
                reasons.append('工作城市符合偏好：' + job['city'])
            else:
                exclusions.append('工作城市不在所选范围：' + job['city'])
        if clean['company_sizes']:
            if not job['company_size']:
                checks.append('公司规模未提供，需核实。')
            elif _key(job['company_size']) in {_key(size) for size in clean['company_sizes']}:
                reasons.append('公司规模符合设置：' + job['company_size'])
            else:
                exclusions.append('公司规模不在所选范围：' + job['company_size'])
        if clean['min_salary_k'] is not None or clean['max_salary_k'] is not None:
            low, high = _salary_range_k(job['salary'])
            if low is None or high is None:
                checks.append('月薪未提供或无法可靠解析，需核实；未推断达到薪资要求。')
            else:
                floor, ceiling = clean['min_salary_k'], clean['max_salary_k']
                if (floor is not None and high < floor) or (ceiling is not None and low > ceiling):
                    exclusions.append(f'公开月薪区间 {low:g}–{high:g}K 与目标薪资不相交。')
                elif (floor is not None and low < floor) or (ceiling is not None and high > ceiling):
                    checks.append(f'公开月薪区间 {low:g}–{high:g}K 仅部分满足设置，具体薪资需核实。')
                else:
                    reasons.append(f'公开月薪区间 {low:g}–{high:g}K 落在设置范围内；实际薪资仍需核实。')
        if clean['max_open_positions']:
            count = _open_count(job['open_positions'])
            if count is None:
                checks.append('公司在招岗位数未提供或无法解析，需核实。')
            elif count > clean['max_open_positions']:
                exclusions.append(f'公司在招岗位数 {count} 超过上限 {clean["max_open_positions"]}。')
            else:
                reasons.append(f'公司在招岗位数 {count} 未超过上限。')
        if clean['require_weekends_off']:
            weekends = _weekends(' '.join(job[field] for field in ('title', 'tags', 'description')))
            if weekends == 'negative':
                exclusions.append('岗位文字出现单休、大小周或否定双休的描述。')
            elif weekends == 'stated':
                reasons.append('岗位文字提到双休；实际休息制度仍需核实。')
            else:
                checks.append('标题、标签及简介没有明确双休信息，需核实。')
        status = 'excluded' if exclusions else 'needs_verification' if checks else 'shortlist'
        results.append({'index': index, 'job': job, 'stable_job_id': stable_id,
                        'duplicate_of': None, 'status': status,
                        'reasons': reasons + exclusions, 'needs_verification': checks,
                        'greeting_draft': draft_greeting(job, clean) if status != 'excluded' else None})
    summary = {status: sum(result['status'] == status for result in results)
               for status in ('shortlist', 'needs_verification', 'excluded', 'duplicate')}
    summary['invalid'] = len(errors)
    return {'source': 'offline_import', 'review_only': True, 'automated_actions': False,
            'summary': summary, 'results': results, 'errors': errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='本地 BOSS 导出岗位筛选；不抓取、不提交、不发消息。')
    parser.add_argument('--jobs', required=True, help='本地 JSON/CSV 岗位导出')
    parser.add_argument('--config', required=True, help='本地 JSON 筛选设置')
    parser.add_argument('--blocked-companies', help='可选：屏蔽公司文本文件，与配置合并')
    parser.add_argument('--output', help='可选：输出 JSON 文件；默认输出到标准输出')
    args = parser.parse_args(argv)
    try:
        config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
        config = validate_config(config)
        if args.blocked_companies:
            imported = import_blocked_companies(Path(args.blocked_companies).read_text(encoding='utf-8-sig'))
            config['excluded_companies'] = _string_list(config['excluded_companies'] + imported, 'excluded_companies')
        result = evaluate_jobs(load_jobs(args.jobs), config)
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(output + '\n', encoding='utf-8')
        else:
            print(output)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f'筛选失败：{exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
