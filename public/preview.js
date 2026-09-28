const examples = {
  knowledge: {
    title: 'AI / 知识库运营',
    context: '示例公司 · 帮助中心与知识内容方向',
    keywords: ['知识库维护', '问题归类', '跨团队协作'],
    evidence: '“整理常见咨询，建立内容更新与审核流程。”',
    why: '这条经历可说明信息梳理和流程维护能力。',
    result: '围绕高频问题整理帮助内容，建立条目更新流程，支持团队保持知识信息一致。',
    pending: '待确认：使用效果与个人贡献边界。'
  },
  user: {
    title: '用户运营',
    context: '示例公司 · 新用户引导方向',
    keywords: ['用户生命周期', '分层触达', '反馈闭环'],
    evidence: '“为学习社群设计新成员引导，并记录常见求助。”',
    why: '这条经历可说明用户分层、沟通设计和反馈整理。',
    result: '设计新成员引导内容，按常见问题调整沟通节奏，并整理反馈用于后续迭代。',
    pending: '待确认：留存变化需要后台记录或复盘材料。'
  },
  product: {
    title: '产品运营',
    context: '示例公司 · 产品上线与反馈方向',
    keywords: ['需求收集', '上线协作', '效果复盘'],
    evidence: '“收集用户反馈，协调内容与产品团队跟进上线问题。”',
    why: '这条经历可说明需求归纳与跨团队推进能力。',
    result: '归纳上线阶段的用户反馈，协调团队明确优先级和处理状态，形成后续改进清单。',
    pending: '待确认：上线效果与本人负责范围。'
  }
};

const buttons = [...document.querySelectorAll('[data-role]')];
const fields = {
  title: document.getElementById('demo-title'),
  context: document.getElementById('demo-context'),
  keywords: document.getElementById('demo-keywords'),
  evidence: document.getElementById('demo-evidence'),
  why: document.getElementById('demo-why'),
  result: document.getElementById('demo-result'),
  pending: document.getElementById('demo-pending')
};

function selectRole(role) {
  const example = examples[role];
  if (!example) return;
  for (const button of buttons) button.setAttribute('aria-pressed', String(button.dataset.role === role));
  fields.title.textContent = example.title;
  fields.context.textContent = example.context;
  fields.evidence.textContent = example.evidence;
  fields.why.textContent = example.why;
  fields.result.textContent = example.result;
  fields.pending.textContent = example.pending;
  fields.keywords.replaceChildren(...example.keywords.map(keyword => {
    const item = document.createElement('span');
    item.textContent = keyword;
    return item;
  }));
}

for (const button of buttons) button.addEventListener('click', () => selectRole(button.dataset.role));
