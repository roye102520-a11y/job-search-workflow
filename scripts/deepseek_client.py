"""Optional server-side DeepSeek adapter. The key never enters browser code or generated files."""
import json
import os
from urllib import request


def complete(prompt, *, max_tokens=1200):
    key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    if not key:
        raise RuntimeError('未配置 DEEPSEEK_API_KEY；工作台本地规则仍可正常运行')
    endpoint = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/chat/completions').strip()
    model = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat').strip()
    body = json.dumps({'model': model, 'messages': [{'role': 'system', 'content': '你是严谨的求职材料编辑，只能使用用户提供的事实；未知信息必须标为待确认，不得编造数字、公司经历或招聘结果。'}, {'role': 'user', 'content': prompt}], 'temperature': 0.2, 'max_tokens': max_tokens}).encode()
    req = request.Request(endpoint, data=body, headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}, method='POST')
    with request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode('utf-8'))
    return payload['choices'][0]['message']['content']
