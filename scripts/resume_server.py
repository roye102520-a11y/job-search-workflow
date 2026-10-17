#!/usr/bin/env python3
"""Loopback-only JD studio. Local files only; no mail, upload or job submission."""
import argparse
import hmac
import importlib
import json
import ipaddress
import secrets
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, parse_qs


FAMILIES = {
    'user-operations': '用户 / 客户运营',
    'ai-content-operations': 'AI 知识库 / 内容运营',
    'implementation-support': '项目交付 / 实施支持',
    'product-operations': '产品助理 / 产品运营',
    'ux-research': 'UX Research｜保守匹配',
}
MAX_BODY = 256 * 1024
ALLOWED_EXTENSIONS = {'.pdf', '.md', '.txt', '.json', '.csv'}
ASSET = Path(__file__).resolve().parents[1] / 'assets' / 'jd-studio.html'
ASSETS = ASSET.parent


def generated_file(case, relative):
    """Resolve one existing generated artifact; never serve the candidate case."""
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ValueError('无效的文件路径')
    pieces = relative.split('/')
    if pieces[0] != 'generated' or any(piece in ('', '.', '..') for piece in pieces):
        raise ValueError('仅可读取 generated 目录内的生成文件')
    case = case.resolve()
    current = case
    for piece in pieces:
        current = current / piece
        if current.is_symlink():
            raise ValueError('不支持通过软链接读取文件')
    target = current.resolve()
    generated = (case / 'generated').resolve()
    if (not generated.is_relative_to(case) or not target.is_relative_to(generated)
            or not target.is_file() or target.suffix.lower() not in ALLOWED_EXTENSIONS):
        raise ValueError('生成文件不存在或类型不可预览')
    return target


def default_generate(case, request, font=None):
    pipeline = importlib.import_module('resume_pipeline')
    return pipeline.generate(case, request, font=font)


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, case, port=8765, font=None, generate_func=None, families=None, host='127.0.0.1'):
        self.case = Path(case).resolve()
        if not self.case.is_dir():
            raise ValueError('案例目录不存在')
        self.font = font
        self.generate_func = generate_func or default_generate
        self.families = dict(families or FAMILIES)
        self.local_token = secrets.token_urlsafe(32)
        self.bind_host = host
        self.generation_lock = threading.Lock()
        super().__init__((host, port), StudioHandler)


class StudioHandler(BaseHTTPRequestHandler):
    server_version = 'LocalResumeStudio/1.0'

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def allowed_request(self):
        port = self.server.server_address[1]
        request_host = self.headers.get('Host', '')
        allowed_hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if self.server.bind_host != '127.0.0.1' and request_host:
            allowed_hosts.add(request_host)
        if request_host not in allowed_hosts and self.server.bind_host == '127.0.0.1':
            self.send_json(403, {'error': '只接受本机页面发起的请求'})
            return False
        origin = self.headers.get('Origin')
        if origin and origin not in {f'http://{host}' for host in allowed_hosts}:
            self.send_json(403, {'error': '请求来源不是当前本地工作台'})
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.send_json(403, {'error': '不接受跨站请求'})
            return False
        return True

    def send_bytes(self, status, content, content_type, extra=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, status, payload):
        self.send_bytes(status, json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                        'application/json; charset=utf-8')

    def do_GET(self):
        if not self.allowed_request():
            return
        path = urlsplit(self.path).path
        if path == '/api/bootstrap':
            self.send_json(200, {'token': self.server.local_token, 'families': self.server.families,
                                 'mode': 'local-review-only'})
        elif path == '/api/ai/config':
            if not self.ai_loopback_only():
                self.send_json(403, {'error': 'DeepSeek 密钥设置仅允许本机访问'})
                return
            if not self.has_token():
                return
            try:
                import deepseek_client
                self.send_json(200, deepseek_client.configuration_status())
            except Exception:
                self.send_json(500, {'error': '无法读取本机 DeepSeek 配置'})
        elif path in ('/api/opportunities', '/api/opportunities/studio'):
            if not self.opportunity_loopback_only():
                self.send_json(403, {'error': '岗位发现数据仅允许本机访问'})
                return
            if not self.has_token():
                return
            try:
                import foreign_opportunities
                if path.endswith('/studio'):
                    key = parse_qs(urlsplit(self.path).query).get('job_key', [''])[0]
                    self.send_json(200, foreign_opportunities.studio_job(self.server.case, key))
                else:
                    self.send_json(200, foreign_opportunities.list_jobs(self.server.case))
            except (OSError, ValueError, TypeError, KeyError) as error:
                self.send_json(400, {'error': str(error)})
        elif path == '/api/career/positioning':
            if not self.opportunity_loopback_only():
                self.send_json(403, {'error': '职业定位资料仅允许本机访问'})
                return
            if not self.has_token():
                return
            try:
                from career_positioning import build_report
                self.send_json(200, build_report(self.server.case))
            except (OSError, ValueError, TypeError, KeyError) as error:
                self.send_json(400, {'error': str(error)})
        elif path in ('/', '/index.html'):
            self.send_page(ASSETS / 'career-workspace.html')
        elif path in ('/demo', '/demo/'):
            self.send_page(ASSETS.parent / 'public/index.html')
        elif path in ('/demo/preview.js', '/demo/styles.css'):
            target = ASSETS.parent / 'public' / path.rsplit('/', 1)[-1]
            self.send_bytes(200, target.read_bytes(), 'text/javascript; charset=utf-8' if target.suffix == '.js' else 'text/css; charset=utf-8')
        elif path == '/studio':
            self.send_page(ASSET)
        elif path == '/strategy':
            self.send_page(ASSETS / 'search-strategy.html')
        elif path == '/api/strategy/followups':
            if not self.has_token():
                return
            try:
                from search_strategy import followups
                self.send_json(200, followups(self.server.case))
            except (OSError, ValueError, TypeError, KeyError) as error:
                self.send_json(400, {'error': str(error)})
        elif path in ('/assets/career-workspace.js', '/assets/career-workspace.css', '/assets/manifest.webmanifest', '/assets/sw.js', '/career-workspace.js', '/career-workspace.css', '/manifest.webmanifest', '/sw.js'):
            target = ASSETS / path.rsplit('/', 1)[-1]
            mime = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.webmanifest': 'application/manifest+json',}.get(target.suffix, 'text/plain; charset=utf-8')
            self.send_bytes(200, target.read_bytes(), mime)
        elif path == '/api/workspace':
            if not self.has_token():
                return
            try:
                import career_workspace
                self.send_json(200, career_workspace.snapshot(self.server.case))
            except (OSError, ValueError, TypeError) as error:
                self.send_json(400, {'error': str(error)})
        elif path == '/api/boss':
            if not self.has_token():
                return
            try:
                import boss_workspace
                self.send_json(200, boss_workspace.state(self.server.case))
            except (OSError, ValueError, TypeError) as error:
                self.send_json(400, {'error': str(error)})
        elif path == '/api/evidence/source':
            if not self.has_token():
                return
            try:
                from resume_pipeline import load_evidence, local
                data = load_evidence(self.server.case)
                ref = parse_qs(urlsplit(self.path).query).get('ref', [''])[0]
                name = ref.split('#')[0]
                if name not in {item['path'] for item in data['sources']}:
                    raise ValueError('原文不在当前已校验的事实来源中')
                target = local(self.server.case, name)
                self.send_json(200, {'source_ref': ref, 'text': target.read_text(encoding='utf-8')})
            except (OSError, ValueError, KeyError):
                self.send_json(400, {'error': '无法读取已校验事实来源，请在档案页复核缓存后重试'})
        elif path == '/api/jd/current':
            if not self.has_token():
                return
            target = self.server.case / 'target-jd.md'
            if not target.is_file() or target.is_symlink():
                self.send_json(404, {'error': '当前案例尚未保存目标 JD'})
            else:
                self.send_json(200, {'jd': target.read_text(encoding='utf-8')})
        elif path.startswith('/resources/'):
            try:
                import career_workspace
                target = career_workspace.document(self.server.case, unquote(path[len('/resources/'):]))
                mime = {'.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.pdf': 'application/pdf'}.get(target.suffix, 'text/plain; charset=utf-8')
                self.send_bytes(200, target.read_bytes(), mime, {'Content-Disposition': "inline; filename*=UTF-8''" + quote(target.name, safe='')})
            except (OSError, ValueError):
                self.send_json(404, {'error': '资料不存在或不在资源索引中'})
        elif path.startswith('/portfolio-preview/'):
            identifier = path[len('/portfolio-preview/'):]
            if not re.fullmatch(r'portfolio-\d{8}T\d{6}-[a-f0-9]{8}', identifier):
                self.send_json(404, {'error': '预览不存在'})
                return
            try:
                import career_workspace
                target = career_workspace.local_file(self.server.case, 'generated/' + identifier + '/website.html')
                self.send_bytes(200, target.read_bytes(), 'text/html; charset=utf-8', {
                    'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'self'; sandbox"})
            except (OSError, ValueError):
                self.send_json(404, {'error': '预览不存在'})
        elif path.startswith('/files/'):
            try:
                target = generated_file(self.server.case, unquote(path[len('/files/'):]))
                mime = 'application/pdf' if target.suffix.lower() == '.pdf' else 'text/plain; charset=utf-8'
                disposition = "inline; filename*=UTF-8''" + quote(target.name, safe='')
                self.send_bytes(200, target.read_bytes(), mime, {'Content-Disposition': disposition})
            except (ValueError, OSError):
                self.send_json(404, {'error': '未找到可访问的生成文件'})
        else:
            self.send_json(404, {'error': '页面不存在'})

    def send_page(self, asset):
        nonce = secrets.token_urlsafe(24)
        content = asset.read_text(encoding='utf-8').replace('__CSP_NONCE__', nonce)
        if asset.name == 'index.html':
            content = content.replace('href="styles.css"', 'href="/demo/styles.css"').replace('<script src="preview.js"', '<script nonce="' + nonce + '" src="/demo/preview.js"')
        policy = (f"default-src 'self'; script-src 'nonce-{nonce}'; style-src 'self' 'nonce-{nonce}'; "
                  "img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; "
                  "base-uri 'none'; form-action 'self'; frame-ancestors 'self'")
        self.send_bytes(200, content.encode('utf-8'), 'text/html; charset=utf-8',
                        {'Content-Security-Policy': policy})

    def has_token(self):
        supplied = self.headers.get('X-Local-Token', '')
        if not hmac.compare_digest(supplied.encode('utf-8'), self.server.local_token.encode('ascii')):
            self.send_json(403, {'error': '页面会话已失效，请刷新后重试'})
            return False
        return True

    def opportunity_loopback_only(self):
        """Never expose real opportunity/JD/evidence data to a LAN client."""
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except (ValueError, IndexError, TypeError):
            return False

    def ai_loopback_only(self):
        """Keep model credentials and candidate context on the local machine."""
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except (ValueError, IndexError, TypeError):
            return False

    def do_POST(self):
        if not self.allowed_request():
            return
        endpoint = urlsplit(self.path).path
        if endpoint not in ('/api/strategy/rank', '/api/generate', '/api/selection', '/api/jd/analyze', '/api/workspace/review', '/api/workspace/portfolio', '/api/workspace/material', '/api/workspace/preferences', '/api/ai/recommend', '/api/ai/key', '/api/boss/settings', '/api/boss/screen', '/api/boss/blocked', '/api/opportunities/import', '/api/opportunities/discover', '/api/opportunities/discover-daily', '/api/opportunities/prepare'):
            self.send_json(404, {'error': '接口不存在'})
            return
        if endpoint.startswith('/api/ai/') and not self.ai_loopback_only():
            self.send_json(403, {'error': 'DeepSeek 设置与调用仅允许本机访问'})
            return
        if endpoint.startswith('/api/opportunities/') and not self.opportunity_loopback_only():
            self.send_json(403, {'error': '岗位发现数据仅允许本机访问'})
            return
        if not self.has_token():
            return
        if self.headers.get('Transfer-Encoding'):
            self.send_json(400, {'error': '不支持分块请求'})
            return
        try:
            length = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            length = -1
        limit = (2048 if endpoint == '/api/ai/key' else
                 9 * 1024 * 1024 if endpoint.endswith('/material') else
                 2 * 1024 * 1024 if endpoint == '/api/boss/screen' else MAX_BODY)
        if not 0 < length <= limit:
            self.send_json(413 if length > limit else 400, {'error': '请求为空或超过大小限制'})
            return
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            self.send_json(415, {'error': '请以 JSON 格式提交 JD'})
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('请求内容不完整，请重试')
            request = json.loads(raw)
            if endpoint.startswith('/api/opportunities/'):
                if not isinstance(request, dict):
                    raise ValueError('请求必须为对象')
                if endpoint.endswith('/import'):
                    if set(request) != {'url'} or not isinstance(request.get('url'), str):
                        raise ValueError('仅接受岗位官网 URL')
                    if len(request['url']) > 2048:
                        raise ValueError('岗位链接过长')
                elif endpoint.endswith('/discover'):
                    if set(request) - {'tenant', 'limit'} or not isinstance(request.get('tenant'), str):
                        raise ValueError('请选择受支持的公开 ATS 租户')
                elif endpoint.endswith('/discover-daily'):
                    if set(request) - {'limit'}:
                        raise ValueError('每日发现仅接受岗位数量上限')
                elif endpoint.endswith('/prepare'):
                    if set(request) != {'job_keys'} or not isinstance(request.get('job_keys'), list):
                        raise ValueError('请提供已发现岗位编号列表')
                if endpoint.endswith(('/discover', '/discover-daily')) and ('limit' in request and (type(request['limit']) is not int or not 1 <= request['limit'] <= 10)):
                    raise ValueError('每轮最多检索 10 个岗位')
                if endpoint.endswith('/prepare') and (not 1 <= len(request['job_keys']) <= 10):
                    raise ValueError('每轮最多准备 10 个岗位')
                self.opportunity_write(endpoint, request)
                return
            if endpoint == '/api/jd/analyze':
                if not isinstance(request, dict) or set(request) != {'jd'} or not isinstance(request['jd'], str):
                    raise ValueError('请提供 JD 正文')
                if not request['jd'].strip() or len(request['jd']) > 100000:
                    raise ValueError('JD 正文为空或过长')
                self.analyze_jd(request['jd'])
                return
            if endpoint not in ('/api/generate', '/api/selection'):
                if not isinstance(request, dict):
                    raise ValueError('请求必须为对象')
                if endpoint == '/api/ai/recommend':
                    self.ai_write(request)
                    return
                if endpoint == '/api/ai/key':
                    self.ai_key_write(request)
                    return
                if endpoint.startswith('/api/boss/'):
                    self.boss_write(endpoint, request)
                    return
                self.workspace_write(endpoint, request)
                return
            allowed = {'jd', 'title', 'company', 'url', 'language', 'family', 'project_priorities', 'selection_budget', 'selected_project_ids'}
            if not isinstance(request, dict) or set(request) - allowed:
                raise ValueError('输入包含不支持的字段')
            if any(not isinstance(value, str) for key, value in request.items() if key not in {'project_priorities', 'selection_budget', 'selected_project_ids'}):
                raise ValueError('JD 与岗位信息须为文字')
            if 'selected_project_ids' in request and not isinstance(request['selected_project_ids'], list):
                raise ValueError('本版项目选择必须是项目 ID 列表')
            if 'selected_project_ids' in request and (
                    any(not isinstance(value, str) for value in request['selected_project_ids']) or
                    len(request['selected_project_ids']) != len(set(request['selected_project_ids']))):
                raise ValueError('本版项目选择必须是不同的项目 ID')
            if 'project_priorities' in request and not isinstance(request['project_priorities'], list):
                raise ValueError('项目优先级必须是经历 ID 列表')
            if not request.get('jd', '').strip():
                raise ValueError('请先粘贴岗位 JD 正文')
            request.setdefault('language', 'zh')
            request.setdefault('family', 'auto')
            if request['language'] not in {'zh', 'en'}:
                raise ValueError('仅支持中文或英文简历')
            if request['family'] != 'auto' and request['family'] not in self.server.families:
                raise ValueError('岗位类型不在当前支持范围')
            if any(len(request.get(name, '')) > limit for name, limit in
                   (('jd', 100000), ('title', 256), ('company', 256), ('url', 2048))):
                raise ValueError('输入过长，请保留 JD 正文和必要岗位信息')
        except (ValueError, UnicodeError) as error:
            self.send_json(400, {'error': str(error) if not isinstance(error, json.JSONDecodeError) else 'JSON 格式有误，请刷新后重试'})
            return
        if not self.server.generation_lock.acquire(blocking=False):
            self.send_json(409, {'error': '已有一份简历正在生成，请完成后重试'})
            return
        try:
            if endpoint == '/api/selection':
                from resume_pipeline import preview_selection
                self.send_json(200, preview_selection(self.server.case, request))
                return
            result = self.server.generate_func(self.server.case, request, font=self.server.font)
            if not isinstance(result, dict) or not isinstance(result.get('files'), dict):
                raise RuntimeError('生成器返回了无效结果')
            for relative in result['files'].values():
                if relative:
                    generated_file(self.server.case, relative)
            self.send_json(200, result)
        except (ValueError, FileNotFoundError) as error:
            self.send_json(400, {'error': str(error)})
        except ImportError:
            self.send_json(503, {'error': '本地生成依赖尚未就绪，请按启动说明检查运行环境'})
        except Exception:
            self.send_json(500, {'error': '本地生成未完成，请检查运行终端或重新启动工作台'})
        finally:
            self.server.generation_lock.release()

    def opportunity_write(self, endpoint, request):
        if not self.server.generation_lock.acquire(blocking=False):
            self.send_json(409, {'error': '正在处理其他工作台任务，请稍后重试'})
            return
        try:
            import foreign_opportunities
            if endpoint.endswith('/import'):
                result = foreign_opportunities.import_url(self.server.case, request)
            elif endpoint.endswith('/discover-daily'):
                from daily_job_search import discover_daily
                result = discover_daily(self.server.case, request.get('limit', 10))
            elif endpoint.endswith('/prepare'):
                from daily_job_search import prepare_selected
                result = prepare_selected(self.server.case, request['job_keys'], font=self.server.font)
            else:
                result = foreign_opportunities.discover(self.server.case, request['tenant'], request.get('limit', 10))
            self.send_json(200, result)
        except (OSError, ValueError, TypeError, KeyError) as error:
            self.send_json(400, {'error': str(error)})
        except Exception:
            self.send_json(502, {'error': '官方岗位读取未完成；未记录为已核验，请稍后重试'})
        finally:
            self.server.generation_lock.release()

    def analyze_jd(self, jd):
        if not self.server.generation_lock.acquire(blocking=False):
            self.send_json(409, {'error': '正在处理其他材料，请稍后重试'})
            return
        try:
            from resume_pipeline import load_evidence
            from jd_gap_analysis import analyze
            self.send_json(200, analyze(jd, load_evidence(self.server.case)))
        except (ValueError, OSError, TypeError, KeyError) as error:
            self.send_json(400, {'error': str(error)})
        except ImportError:
            self.send_json(503, {'error': '本地分析模块未就绪，请检查工作台安装'})
        except Exception:
            self.send_json(500, {'error': '岗位分析未完成，请检查运行终端'})
        finally:
            self.server.generation_lock.release()

    def workspace_write(self, endpoint, request):
        if not self.server.generation_lock.acquire(blocking=False):
            self.send_json(409, {'error': '正在保存其他材料，请稍后重试'})
            return
        try:
            import career_workspace
            if endpoint == '/api/strategy/rank':
                from search_strategy import run
                action = run
            elif endpoint.endswith('/preferences'):
                from career_workspace import save_preferences
                action = save_preferences
            elif endpoint.endswith('/material'):
                from material_intake import ingest
                action = ingest
            else:
                action = career_workspace.save_review if endpoint.endswith('/review') else career_workspace.build_portfolio
            self.send_json(200, action(self.server.case, request))
        except (ValueError, OSError, TypeError, KeyError) as error:
            self.send_json(400, {'error': str(error)})
        except Exception:
            self.send_json(500, {'error': '工作台保存未完成，请检查终端'})
        finally:
            self.server.generation_lock.release()

    def boss_write(self, endpoint, request):
        if not self.server.generation_lock.acquire(blocking=False):
            self.send_json(409, {'error': '正在保存其他材料，请稍后重试'})
            return
        try:
            import boss_workspace
            action = {'/api/boss/settings': boss_workspace.save_settings,
                      '/api/boss/screen': boss_workspace.screen_jobs,
                      '/api/boss/blocked': boss_workspace.import_blocked}[endpoint]
            self.send_json(200, action(self.server.case, request))
        except (ValueError, OSError, TypeError, KeyError) as error:
            self.send_json(400, {'error': str(error)})
        except Exception:
            self.send_json(500, {'error': 'BOSS 本地筛选未完成，请检查终端'})
        finally:
            self.server.generation_lock.release()

    def ai_write(self, request):
        """Call DeepSeek only from the server, after the user explicitly clicks the AI action."""
        prompt = request.get('prompt', '') if isinstance(request, dict) else ''
        if not isinstance(prompt, str) or not 20 <= len(prompt) <= 12000:
            self.send_json(400, {'error': 'AI 请求应为 20–12000 字的文字'})
            return
        if not self.server.generation_lock.acquire(blocking=False):
            self.send_json(409, {'error': '已有材料任务正在运行，请稍后重试'})
            return
        try:
            from deepseek_client import complete
            self.send_json(200, {'text': complete(prompt)})
        except RuntimeError as error:
            self.send_json(503, {'error': str(error)})
        except Exception:
            self.send_json(502, {'error': 'DeepSeek 暂时不可用；本地推荐仍可继续使用'})
        finally:
            self.server.generation_lock.release()

    def ai_key_write(self, request):
        if not isinstance(request, dict):
            self.send_json(400, {'error': '密钥设置格式无效'})
            return
        if request.get('action') == 'save' and set(request) == {'action', 'api_key'}:
            action = 'save'
        elif request == {'action': 'clear'}:
            action = 'clear'
        else:
            self.send_json(400, {'error': '请选择保存或清除本机密钥'})
            return
        if not self.server.generation_lock.acquire(blocking=False):
            self.send_json(409, {'error': 'DeepSeek 请求正在运行，请稍后重试'})
            return
        try:
            import deepseek_client
            if action == 'save':
                deepseek_client.save_local_key(request['api_key'])
            else:
                deepseek_client.clear_local_key()
            self.send_json(200, deepseek_client.configuration_status())
        except ValueError as error:
            self.send_json(400, {'error': str(error)})
        except Exception:
            self.send_json(500, {'error': '本机密钥保存失败，请检查本机权限'})
        finally:
            self.server.generation_lock.release()

    def do_OPTIONS(self):
        if self.allowed_request():
            self.send_json(405, {'error': '此工作台不开放跨站 API'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, type=Path)
    parser.add_argument('--port', default=8765, type=int)
    parser.add_argument('--font', type=Path)
    parser.add_argument('--host', default='127.0.0.1', help='默认仅本机；手机局域网预览可用 0.0.0.0，但请只在可信网络使用')
    args = parser.parse_args()
    try:
        server = StudioServer(args.case, args.port, args.font, host=args.host)
    except (ValueError, OSError) as error:
        parser.exit(2, 'ERROR: ' + str(error) + '\n')
    display_host = '127.0.0.1' if args.host == '0.0.0.0' else args.host
    print(f'JD 简历工作台：http://{display_host}:{server.server_address[1]}', flush=True)
    print(('局域网预览模式：请仅在可信网络使用；' if args.host != '127.0.0.1' else '仅在本机生成审阅稿；') + '不会发送邮件或提交申请。Ctrl+C 停止。', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
