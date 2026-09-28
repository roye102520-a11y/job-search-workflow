"""Extract supplied documents locally; keep unconfirmed material out of the fact bank."""
import base64
import binascii
import hashlib
import io
import json
from pathlib import Path
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

MAX_FILE = 6 * 1024 * 1024


def extract(filename, raw):
    suffix = Path(filename).suffix.lower()
    if suffix in ('.txt', '.md'):
        return raw.decode('utf-8-sig')
    if suffix == '.docx':
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entry = archive.getinfo('word/document.xml')
            if entry.file_size > 12 * 1024 * 1024:
                raise ValueError('Word 正文过大')
            root = ET.fromstring(archive.read(entry))
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            return '\n'.join(''.join(p.itertext()) for p in root.findall('.//w:p', ns))
    if suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted or len(reader.pages) > 100:
            raise ValueError('请提供未加密、100 页以内的 PDF')
        return '\n'.join(page.extract_text() or '' for page in reader.pages)
    raise ValueError('支持 PDF、DOCX、Markdown 和 UTF-8 文本')


def ingest(case, request):
    from career_workspace import local_file
    case = Path(case).resolve()
    if not isinstance(request, dict) or set(request) != {'name', 'content', 'kind'}:
        raise ValueError('材料字段无效')
    name = request['name']
    if not isinstance(name, str) or not name or len(name) > 180 or '/' in name or '\\' in name or any(ord(c) < 32 for c in name):
        raise ValueError('材料文件名无效')
    if request['kind'] not in ('resume', 'portfolio') or not isinstance(request['content'], str):
        raise ValueError('请选择简历或作品集')
    try:
        raw = base64.b64decode(request['content'], validate=True)
        if not raw or len(raw) > MAX_FILE:
            raise ValueError('单份材料须为 1 字节至 6 MB')
        content = extract(name, raw).strip()
    except (binascii.Error, UnicodeError, zipfile.BadZipFile, KeyError, ET.ParseError) as error:
        raise ValueError('文件无法读取，请检查格式或另存为文本') from error
    if len(content) < 20:
        raise ValueError('未读取到足够文字；扫描件请先 OCR 或提供文字版')
    if len(content) > 200000:
        raise ValueError('材料正文过长，请按项目拆分')
    digest = hashlib.sha256(raw).hexdigest()
    folder = local_file(case, 'material-inbox')
    folder.mkdir(exist_ok=True)
    for existing in folder.glob('*/intake.json'):
        prior = json.loads(local_file(case, existing.relative_to(case).as_posix()).read_text())
        if prior.get('sha256') == digest and prior.get('kind') == request['kind']:
            return prior
    identifier = uuid.uuid4().hex
    destination = local_file(case, 'material-inbox/' + identifier)
    destination.mkdir()
    (destination / ('source' + Path(name).suffix.lower())).write_bytes(raw)
    (destination / 'extracted.txt').write_text(content, encoding='utf-8')
    paragraphs = [line.strip() for line in content.splitlines() if line.strip()]
    result = {'id': identifier, 'name': name, 'kind': request['kind'], 'sha256': digest,
              'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'needs_review',
              'characters': len(content), 'excerpt': paragraphs[:12],
              'text_path': 'material-inbox/' + identifier + '/extracted.txt',
              'note': '已提取原文与摘要摘录，尚未合并事实。请在 Codex 中综合材料，核对冲突、数字与个人贡献。'}
    (destination / 'intake.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result
