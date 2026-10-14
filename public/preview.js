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

const $ = id => document.getElementById(id);
function show(panel, focus=true){
  if(![...document.querySelectorAll('[data-section]')].some(s=>s.dataset.section===panel))panel='overview';
  document.querySelectorAll('[data-section]').forEach(s=>s.hidden=s.dataset.section!==panel);
  document.querySelectorAll('[data-panel]').forEach(b=>{if(b.dataset.panel===panel)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  if(location.hash!=='#'+panel)history.pushState(null,'','#'+panel);
  window.scrollTo({top:0,behavior:'instant'});if(focus){const heading=document.querySelector('[data-section="'+panel+'"] h1');heading.tabIndex=-1;heading.focus({preventScroll:true});}
}
document.querySelectorAll('[data-panel]').forEach(b=>b.addEventListener('click',()=>show(b.dataset.panel)));
document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>show(b.dataset.go)));
const scenarios={
  new:['上传简历，建立求职档案。','从已有简历或一段经历开始，核对事实与来源，再决定申请什么岗位。','查看建档方式','assets','尚未设置。建档时可选择方向，已有目标可直接使用。','还没有档案。没有简历也可以先记录一段经历。','暂无岗位。确认事实库后，粘贴一个完整 JD 开始。','暂无材料。'],
  complete:['分析一个新岗位。','已有完整简历，可以跳过建档。完整 JD 是分析要求与证据的起点。','体验岗位分析','resume','示例目标：用户运营','合成档案已提供经历与教育，个人贡献仍待确认。','示例公司 · 用户运营 · 尚未投递','示例简历：待核对来源和版面。'],
  transition:['先看 AI 产品岗位需要什么。','用现有运营经历和个人 AI 实践对照 JD；相邻经验只标记部分相关。','查看证据与差距','resume','示例目标：从运营转型 AI 产品','运营事实与个人 AI 实践分开记录，生产环境能力未知。','示例公司 · AI 内容运营 · 待研究','尚需核对职责深度；练习不能写成真实业务成果。'],
  multi:['为三个方向分别选材。','同一事实库支持独立材料；每份 JD 保留自己的取舍与版本。','比较示例岗位','resume','示例目标：用户运营 / AI 内容运营 / 产品运营','复用同一合成档案，目标不同不会修改事实。','三份预设合成岗位；均未投递','三个方向分别审阅，不混用 JD 或提交版本。'],
  single:['直接修改这一份 JD 简历。','不必重复建档。分析岗位、调整项目优先级，再生成独立版本。','查看这个 JD','resume','沿用已有目标，仅处理当前岗位','沿用已提供的合成档案。','示例公司 · 产品运营 · 待准备','当前版本待人工审阅；修改后保留旧版本。']
};
$('scenario').addEventListener('change',()=>{const key=$('scenario').value,t=scenarios[key];for(const [id,v] of [['next-title',t[0]],['next-copy',t[1]],['target',t[4]],['profile-state',t[5]],['recent-jobs',t[6]],['unfinished',t[7]]])$(id).textContent=v;$('next-action').textContent=t[2];$('next-action').dataset.go=t[3];$('continue-action').hidden=key==='new';});
$('use-profile').addEventListener('click',()=>{$('scenario').value='complete';$('scenario').dispatchEvent(new Event('change'));show('overview');});
$('demo-review').addEventListener('click',()=>{$('demo-status').hidden=false;$('demo-status').textContent='合成材料进入人工审阅：请核对原始事实、个人贡献和未证实的结果。下一步在本地生成独立材料；当前没有真实投递。';});
window.addEventListener('popstate',()=>{if(location.hash!=='#use')show(location.hash.slice(1)||'overview');});
selectRole('knowledge');
if(location.hash && location.hash!=='#use')show(location.hash.slice(1),false);
