"""Optional server-side DeepSeek adapter. The key never enters browser code or generated files."""
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from urllib import request


def _credential_path():
    """Return a per-user config path outside the project and candidate case."""
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local'))
        return base / 'Career Studio' / 'deepseek.json'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'Career Studio' / 'deepseek.json'
    base = Path(os.environ.get('XDG_CONFIG_HOME') or (Path.home() / '.config'))
    return base / 'career-studio' / 'deepseek.json'


def _read_local_key():
    path = _credential_path()
    try:
        if path.is_symlink() or not path.is_file():
            return ''
        mode = path.stat().st_mode
        if not stat.S_ISREG(mode) or (os.name != 'nt' and stat.S_IMODE(mode) & 0o077):
            return ''
        payload = json.loads(path.read_text(encoding='utf-8'))
        key = payload.get('api_key', '') if isinstance(payload, dict) else ''
        return key.strip() if isinstance(key, str) else ''
    except (OSError, UnicodeError, ValueError):
        return ''


def configured_key():
    """Environment configuration keeps precedence for backward compatibility."""
    return os.environ.get('DEEPSEEK_API_KEY', '').strip() or _read_local_key()


def configuration_status():
    if os.environ.get('DEEPSEEK_API_KEY', '').strip():
        return {'configured': True, 'source': 'environment'}
    if _read_local_key():
        return {'configured': True, 'source': 'local'}
    return {'configured': False, 'source': None}


def save_local_key(value):
    if not isinstance(value, str):
        raise ValueError('请输入有效的 DeepSeek API Key')
    key = value.strip()
    if not re.fullmatch(r'[\x21-\x7e]{20,512}', key):
        raise ValueError('API Key 应为 20–512 位、不含空格的可见字符')
    path = _credential_path()
    folder = path.parent
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if folder.is_symlink():
        raise ValueError('本机密钥目录不安全，无法保存')
    if os.name != 'nt':
        folder.chmod(0o700)
    fd, temp_name = tempfile.mkstemp(prefix='.deepseek-', dir=str(folder))
    try:
        if os.name != 'nt':
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(json.dumps({'api_key': key}, ensure_ascii=True))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        if os.name != 'nt':
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def clear_local_key():
    path = _credential_path()
    if path.is_symlink():
        raise ValueError('本机密钥文件类型异常，未执行删除')
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def complete(prompt, *, max_tokens=1200):
    key = configured_key()
    if not key:
        raise RuntimeError('尚未配置 DeepSeek API Key；工作台本地规则仍可正常运行')
    endpoint = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/chat/completions').strip()
    model = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat').strip()
    body = json.dumps({'model': model, 'messages': [{'role': 'system', 'content': '你是严谨的求职材料编辑，只能使用用户提供的事实；未知信息必须标为待确认，不得编造数字、公司经历或招聘结果。'}, {'role': 'user', 'content': prompt}], 'temperature': 0.2, 'max_tokens': max_tokens}).encode()
    req = request.Request(endpoint, data=body, headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}, method='POST')
    with request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode('utf-8'))
    return payload['choices'][0]['message']['content']
