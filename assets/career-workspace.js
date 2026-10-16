'use strict';
const $ = id => document.getElementById(id);
let token = '', workspace = null, saving = false, installPrompt = null, bossState = {settings:null,screen:null}, opportunityJobs = [];
const families = {'user-operations':'用户 / 客户运营','ai-content-operations':'AI 知识库 / 内容运营','implementation-support':'项目交付 / 实施支持','product-operations':'产品助理 / 产品运营'};
const stages = {discovered:'已发现',shortlisted:'已筛选',preparing:'准备材料',ready:'可人工审核',submitted:'已投递',assessment:'测评',interview:'面试',offer:'Offer',rejected:'已拒绝',withdrawn:'已撤回',closed:'已关闭'};
const dimensions = ['证据','结构','岗位相关性','个人贡献','可信度'];
function node(tag, text, className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function clear(id){$(id).replaceChildren();return $(id);}
function notice(message){$('notice').textContent=message;}
function localURL(prefix, path){return prefix+path.split('/').map(encodeURIComponent).join('/');}
function link(text, href){const a=node('a',text);a.href=href;a.target='_blank';a.rel='noopener noreferrer';return a;}
function externalLink(text, value){try{const url=new URL(value);return ['http:','https:'].includes(url.protocol)&&!url.username&&!url.password?link(text,url.href):node('span','未提供网址');}catch{return node('span','未提供网址');}}
async function api(path, body){const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'X-Local-Token':token,...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});const result=await response.json();if(!response.ok)throw new Error(result.error||'操作未完成');return result;}
function show(panel, focus=true){const known=[...document.querySelectorAll('[data-section]')].some(s=>s.dataset.section===panel);if(!known)panel='overview';document.querySelectorAll('[data-section]').forEach(s=>s.hidden=s.dataset.section!==panel);document.querySelectorAll('[data-panel]').forEach(b=>{if(b.dataset.panel===panel)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});if(panel==='resume'&&!$('studio-frame').getAttribute('src'))$('studio-frame').src='/studio';if(location.hash!=='#'+panel)history.pushState(null,'','#'+panel);window.scrollTo({top:0,behavior:'instant'});if(focus){const heading=document.querySelector('[data-section="'+panel+'"] h1');if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true});}}}
function bar(label,value,max,color='#0071e3'){
  const row=node('div',undefined,'bar-row');row.append(node('span',label));
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 100 8');svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('class','bar-track');svg.setAttribute('role','img');svg.setAttribute('aria-label',label+'：'+(value===null?'未评分':value));
  for(const [width,fill] of [[100,'#eeeeF1'],[value===null?0:Math.max(0,Math.min(100,100*value/Math.max(max,1))),color]]){const r=document.createElementNS(ns,'rect');r.setAttribute('width',String(width));r.setAttribute('height','8');r.setAttribute('rx','4');r.setAttribute('fill',fill);svg.append(r);}row.append(svg,node('span',value===null?'—':String(value),'bar-value'));return row;
}
function renderOverview(data){
  const task=data.task,action=task.primary_action;
  const texts={upload:['上传简历，建立求职档案。','准备 PDF、Word 或文字简历。提取原文后，需要核对经历和个人贡献。','上传简历','assets'],review:['先核对已导入的经历。','材料已保留原文；请确认事实、冲突和来源，再更新档案。','核对我的档案','assets'],analyze:['分析一个新岗位。','已有事实库可以直接使用。粘贴完整 JD，查看要求、证据与选材。','分析新岗位','resume']};
  const t=texts[action];$('next-title').textContent=t[0];$('next-copy').textContent=t[1];$('next-action').textContent=t[2];$('next-action').dataset.go=t[3];
  $('continue-action').hidden=!data.history.length;
  $('owner').textContent=data.name+' · '+data.source;
  $('current-target').textContent='求职目标：'+(task.current_target.length?task.current_target.join(' / '):'尚未设置，可在「投递进度」设置岗位偏好');
  $('profile-completeness').textContent='档案字段：'+task.completed_fields.length+' / '+task.field_total+' 已提供'+(task.missing_fields.length?' · 待补充 '+task.missing_fields.join('、'):'')+'；字段完整不代表事实已全部确认。';
  $('pending-facts').textContent='待确认事实：'+task.pending_facts+' 项'+(task.profile_valid?' · 来源校验通过':' · 事实库尚未就绪或来源需要复核');
  for(const [id,items,empty] of [['recent-jobs',task.recent_jobs,'暂无岗位。准备好事实库后，可直接分析新 JD。'],['unfinished-materials',task.unfinished_materials,'暂无待准备材料。'],['recent-submissions',task.recent_submissions,'暂无确认投递记录。']]){
    const box=clear(id);items.forEach(item=>{const row=node('div',undefined,'resource-item');row.append(node('strong',(item.company||'公司待确认')+' · '+(item.title||item.role||'岗位')),node('p',item.stale?'事实源已更新，请重新生成；旧版本仍可查看':item.next_action||'本地审阅记录'));box.append(row);});if(!items.length)box.append(node('p',empty));
  }
  const chart=clear('evidence-chart'),counts=Object.keys(families).map(key=>data.entries.flatMap(e=>e.bullets||[]).filter(b=>(b.tags||[]).includes(key)).length);
  Object.entries(families).forEach(([key,label],i)=>chart.append(bar(label,counts[i],Math.max(...counts,1))));
  $('confirmed-count').textContent=data.stats.submitted;
  const distribution=clear('stage-chart');for(const [stage,count] of Object.entries(data.stats.stages))distribution.append(node('span',(stages[stage]||stage)+' '+count,'stage-chip'));
  const next=clear('next-steps');(data.next_steps.length?data.next_steps:[task.profile_valid?'选一个目标 JD，先检查硬条件和直接证据。':'核对资料中的事实、日期和个人贡献；由 Codex 更新事实库后刷新页面。']).forEach(text=>next.append(node('li',text)));
}
function resourceItem(name){const item=node('div',undefined,'resource-item');if(/\.(docx|pdf)$/.test(name))item.append(link(name.split('/').pop(),localURL('/resources/',name)));else{const b=node('button',name.split('/').pop());b.type='button';b.addEventListener('click',()=>viewDocument(name));item.append(b);}return item;}
async function viewDocument(path){$('document-title').textContent=path.split('/').pop();$('document-content').textContent='正在读取…';$('document-dialog').showModal();try{const response=await fetch(localURL('/resources/',path),{cache:'no-store'});if(!response.ok)throw new Error('资料读取失败');$('document-content').textContent=await response.text();}catch(error){$('document-content').textContent=error.message;}}
function renderAssets(data){
  const intake=clear('material-history');(data.materials||[]).forEach(m=>{const d=node('details',undefined,'surface');d.append(node('summary',m.name+' · '+m.characters+' 字 · 待复核'));d.append(node('p',m.note));(m.excerpt||[]).forEach(t=>d.append(node('p',t)));intake.append(d);});
  const choice=$('portfolio-resume'),previous=choice.value;choice.replaceChildren(new Option('当前完整事实库',''));data.history.filter(h=>!h.synthetic&&h.files.pdf).forEach(h=>choice.add(new Option(h.company+' · '+h.title+' · '+h.id,h.id)));choice.value=previous;
  const companies=clear('company-shortlist');if(data.documents.includes('company-shortlist.md'))companies.append(resourceItem('company-shortlist.md'));else companies.append(node('p','请在 Codex 中按公司偏好检索官网岗位。'));
  const drafts=clear('portfolio-history');(data.portfolios||[]).forEach(d=>{const row=node('div',undefined,'resource-item');row.append(node('span',d.id+' · 未发布　'),link('内容稿',localURL('/files/',d.markdown)),document.createTextNode('　'),link('网站预览 ↗',d.preview));drafts.append(row);});
  const selected=new Set([...document.querySelectorAll('[data-project]:checked')].map(x=>x.value));const gallery=clear('project-gallery');
  data.projects.forEach((project,index)=>{const card=node('article',undefined,'project');const art=node('div',undefined,'project-art');const title=project.title_zh||project.id;art.append(node('span',title.split('｜')[0].split(' ')[0]));const body=node('div',undefined,'project-content');body.append(node('h3',title),node('p',project.employment_zh+' · '+project.dates));const list=node('ul');(project.bullets||[]).slice(0,2).forEach(b=>list.append(node('li',b.zh)));body.append(list);const links=node('div',undefined,'links');if(project.website)links.append(externalLink('查看项目 ↗',project.website));if(project.github)links.append(externalLink('GitHub ↗',project.github));body.append(links,node('p','项目状态与线上链接来自档案；真实用户结果仍需核实。','caption'));const select=node('label',undefined,'project-select');const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.value=project.id;checkbox.dataset.project='';checkbox.checked=selected.size?selected.has(project.id):true;select.append(checkbox,node('span','加入本次作品集'));card.append(art,body,select);gallery.append(card);});if(!data.projects.length)gallery.append(node('p','尚无项目证据，请先在 Codex 中整理个人项目。','empty-state'));
  const sources=clear('source-documents');data.documents.filter(n=>!n.includes('/')&&n!=='direction-review.md').forEach(n=>sources.append(resourceItem(n)));
  const versions=clear('resume-versions');data.documents.filter(n=>n.startsWith('resume-versions/')).forEach(n=>versions.append(resourceItem(n)));if(!versions.children.length)versions.append(node('p','暂无历史 Word 简历','caption'));
  const gaps=clear('unconfirmed');(Array.isArray(data.unconfirmed)?data.unconfirmed:Object.values(data.unconfirmed||{})).forEach(item=>gaps.append(node('div',typeof item==='string'?item:(item.note||JSON.stringify(item)),'resource-item')));if(!gaps.children.length)gaps.append(node('p','请查看事实库中的待确认条目。','caption'));
  const site=clear('website-link');if(data.website)site.append(externalLink('打开当前个人网站 ↗',data.website));else site.append(node('p','档案尚未记录个人网站。','caption'));
}
function renderHistory(data){const box=clear('history');const items=data.history.filter(h=>$('include-tests').checked||!h.synthetic);items.forEach(item=>{const row=node('article',undefined,'history-item');const info=node('div');info.append(node('h3',item.title),node('p',item.company+' · '+(item.label||'方向待确认')+' · '+item.blockers+' 项必需条件待核实'),node('p',item.id+(item.stale?' · 事实已更新，需重新生成':'')+(item.synthetic?' · 合成验收':''),'caption'));const links=node('div',undefined,'links');for(const [key,label] of [['pdf','PDF ↗'],['match','匹配报告'],['email','邮件草稿'],['review','复核项']])if(item.files[key])links.append(link(label,localURL('/files/',item.files[key])));row.append(info,links);box.append(row);});if(!items.length)box.append(node('p','暂无此范围的生成材料。粘贴 JD 后，每次都会保留独立版本。','empty-state'));}
function renderApplications(data){const board=clear('application-board');const groups=[['待研究',['discovered']],['待准备',['shortlisted','preparing']],['可人工审核',['ready']],['已投递',['submitted','assessment']],['面试中',['interview','offer']],['已结束',['rejected','withdrawn','closed']]];for(const [label,statuses] of groups){const items=data.applications.filter(a=>statuses.includes(a.status));const col=node('article',undefined,'board-column');const heading=node('h3',label);heading.append(node('span',String(items.length),'caption'));col.append(heading);items.forEach(item=>{const card=node('div',undefined,'job-card');card.append(node('h4',item.company),node('p',item.role),node('p',stages[item.status]||item.status),node('p','执行：'+(item.execution_status||'idle')+' · 同步：'+(item.sync_status||'not_requested')));if(item.resume_variant)card.append(node('p','专属简历版本：'+item.resume_variant));if(item.resume_path)card.append(link('查看简历 ↗',localURL('/files/',item.resume_path)));if(item.email_path){card.append(node('p','求职邮件草稿尚未发送。'));card.append(link('本地查看邮件草稿 ↗',localURL('/files/',item.email_path)));}if(item.channel||item.submitted_at)card.append(node('p','渠道：'+(item.channel||'未知')+' · 提交时间：'+(item.submitted_at||'未知')));if(item.receipt_path)card.append(node('p','回执：已记录（'+item.receipt_path+'）'));if(item.next_action)card.append(node('p',item.next_action));if(item.url)card.append(externalLink('官网岗位 ↗',item.url));col.append(card);});if(!items.length)col.append(node('p','暂无记录','caption'));board.append(col);}
  $('outcome-note').textContent=data.stats.submitted?'已有 '+data.stats.submitted+' 个岗位包含确认提交事件；详细分组与观察期请打开报告。':'当前没有带确认提交事件的真实申请，尚不能判断哪个方向或版本更有效。';const report=clear('direction-report');if(data.documents.includes('direction-review.md'))report.append(resourceItem('direction-review.md'));
  const picker=$('review-job'),prior=picker.value;picker.replaceChildren(new Option('暂不关联',''));data.applications.forEach(a=>picker.add(new Option(a.company+' · '+a.role,a.job_key)));picker.value=prior;
}
function renderPreferences(data){
  const selected=data.preferences||{};
  for(const [key,id] of [['categories','preference-categories'],['locations','preference-locations'],['requests','preference-requests']]){const box=clear(id);(data.preference_options[key]||[]).forEach(value=>{const label=node('label','', 'check-pill');const input=document.createElement('input');input.type='checkbox';input.name=key;input.value=value;input.checked=(selected[key]||[]).includes(value);label.append(input,node('span',value));box.append(label);});}
  const list=clear('recommendations');(data.recommendations||[]).forEach(item=>{const card=node('article',undefined,'recommendation-card');const head=node('div',undefined,'recommendation-head');head.append(node('div',undefined,'recommendation-score'));head.firstChild.append(node('strong',String(item.score)),node('span','规则分'));head.append(node('div'));head.lastChild.append(node('h3',item.title),node('p',item.company+' · '+item.locations.join(' / ')));card.append(head);card.append(node('p','事实标签关联：'+(item.evidence.length?item.evidence.join('、'):'当前简历证据较少，建议先读 JD')));card.append(node('p',item.status,'caption'));if(item.url)card.append(externalLink('打开岗位原链接 ↗',item.url));list.append(card);});if(!list.children.length)list.append(node('p','暂无符合当前偏好的推荐，请放宽地点或岗位类别。','empty-state'));
}
const opportunityTypes={internship:'实习',full_time:'正式岗位',graduate_program:'Graduate / Trainee',project_freelance:'项目制 / Freelance',unknown:'类型待核实'};
const qualificationLabels={eligible:'官方确认可申请',ineligible:'资格不符合',needs_confirmation:'毕业资格待确认',not_applicable:'不适用'};
const requirementLabels={supported:'有直接证据',partial:'部分证据',unknown:'待核实',not_met:'明确不满足'};
function renderOpportunityJobs(){
  const list=clear('opportunity-list'),filter=$('opportunity-type-filter').value;
  const rows=opportunityJobs.filter(job=>filter==='all'||(job.match?.employment_category||'unknown')===filter);
  $('opportunity-status').textContent=opportunityJobs.length?'共 '+opportunityJobs.length+' 条本地岗位记录；核验状态与求职状态分开显示。':'暂无通过本地岗位发现流程保存的岗位。导入官方 JD 后会在这里显示；静态推荐不作为已核验岗位。';
  rows.forEach(job=>{
    const match=job.match||{},verification=job.verification||{},card=node('article',undefined,'recommendation-card');
    const application=(workspace?.applications||[]).find(item=>item.job_key===job.job_key)||{};
    const head=node('div',undefined,'recommendation-head'),score=node('div',undefined,'recommendation-score');
    score.append(node('strong',match.grade||'U'),node('span','匹配级别'));
    const title=node('div');title.append(node('h3',job.title||'岗位名称待核实'),node('p',(job.company||'公司待核实')+' · '+(job.location||'地点未知')));
    head.append(score,title);card.append(head);
    const category=match.employment_category||'unknown';
    card.append(node('p','类型：'+(opportunityTypes[category]||'类型待核实')+' · JD 标注：'+(job.employment_type||'未知')));
    const qualification=match.internship_qualification||{status:'not_applicable',reason:'未提供资格判断'};
    if(category==='internship')card.append(node('p','毕业资格：'+(qualificationLabels[qualification.status]||'待核实')+' · '+qualification.reason));
    const pay=match.posted_compensation||{paid_status:'unknown',published:'未知（来源未披露）'};
    const payLabel={paid:'来源明确为有薪',unpaid:'来源明确为无薪',unknown:'有薪状态未知'}[pay.paid_status]||'有薪状态未知';
    const preference=match.salary?.floor_text||'未知';
    card.append(node('p','薪资：'+pay.published+' · '+payLabel+' · 原薪资偏好：'+preference));
    const mode=match.work_mode||{label:'未知',reason:'来源未说明'};
    card.append(node('p','工作模式：'+(mode.label||'未知')+' · '+(mode.reason||'')+' · 发布时间：'+(job.posted_date_text||'未知')));
    const verified=verification.status==='verified_open'&&verification.verified_at?new Date(verification.verified_at).toLocaleString('zh-CN'):'未知（当前未核验）';
    card.append(node('p','官网状态：'+(verification.status==='verified_open'?'已核验可申请':verification.status==='closed'?'官方已关闭':verification.status==='stale'?'核验已过期':'待核实')+' · 最后核验：'+verified,'caption'));
    const executionLabels={idle:'未执行外部投递',filling:'操作中',blocked:'已阻止',submission_unknown:'提交结果未知'};
    card.append(node('p','Career Studio 状态：'+(stages[application.status]||'已发现')+' · '+(executionLabels[application.execution_status]||'未执行外部投递'),'caption'));
    if(application.resume_variant)card.append(node('p','专属简历：'+application.resume_variant+(application.resume_path?' · ':'')+(application.resume_path?'':'暂未生成')));
    else if(application.prepared_materials?.length)card.append(node('p','已生成本地审阅材料：'+application.prepared_materials.map(item=>item.language==='en'?'英文':'中文').join('、')));
    if(application.email_path){const email=link('查看本地求职邮件草稿 ↗',localURL('/files/',application.email_path));card.append(email,node('p','邮件为审阅草稿，尚未发送。','caption'));}
    if(application.channel||application.submitted_at||application.receipt_path){
      card.append(node('p','投递渠道：'+(application.channel||'未知')+' · 提交时间：'+(application.submitted_at||'未知')+' · 回执：'+(application.receipt_path?'已记录':'未知')));
    }
    if(application.resume_path)card.append(link('查看当前专属简历 ↗',localURL('/files/',application.resume_path)));
    const reasons=node('details');reasons.append(node('summary','查看匹配理由、条件证据与缺口'));
    const reasonBody=node('div');
    (match.grade_reasons||[]).forEach(text=>reasonBody.append(node('p','结论：'+text)));
    if(match.target_priority)reasonBody.append(node('p','方向优先级：'+match.target_priority+' · '+(match.target_label||'')+'；这是规则归类，不是录用概率。'));
    (match.hard_reasons||[]).forEach(text=>reasonBody.append(node('p','不符合：'+text)));
    (match.warnings||[]).forEach(text=>reasonBody.append(node('p','待核实：'+text)));
    (match.requirements||[]).forEach(item=>{
      const refs=(item.evidence_refs||[]).slice(0,3).join('、');
      reasonBody.append(node('p',(item.level==='required'?'必需':'加分')+' · '+(requirementLabels[item.status]||'待核实')+'：'+item.text+(refs?' · 事实来源：'+refs:'')));
    });
    reasons.append(reasonBody);card.append(reasons);
    const actions=node('div',undefined,'links');
    if(job.url)actions.append(externalLink('打开官方 JD ↗',job.url));
    const studio=node('button',typeof job.jd==='string'&&job.jd.length>=40?'送入 JD Studio':'JD 不完整，暂不能导入','secondary');studio.type='button';studio.disabled=!(typeof job.jd==='string'&&job.jd.length>=40);
    studio.addEventListener('click',()=>{sessionStorage.setItem('career-studio-jd-prefill',JSON.stringify({jd:job.jd,title:job.title||'',company:job.company||'',url:job.url||'',auto_generate:false}));location.assign('/studio');});
    actions.append(studio);
    const qualificationStatus=qualification.status||'needs_confirmation';
    const canPrepare=verification.status==='verified_open'&&['A','B'].includes(match.grade)
      &&(category!=='internship'||qualificationStatus==='eligible')
      &&pay.paid_status!=='unpaid'&&typeof job.jd==='string'&&job.jd.trim().length>=40
      &&!['submitted','assessment','interview','offer','rejected','withdrawn','closed'].includes(application.status);
    const prepare=node(application.resume_variant?'重新生成中英审阅材料':'生成中英审阅材料','secondary');prepare.type='button';prepare.disabled=!canPrepare;
    prepare.title=canPrepare?'仅在本地生成简历与邮件草稿；不会发送或提交。':'需完整 JD、当前官网核验、A/B 级匹配、符合的毕业资格及非无薪条件。';
    prepare.addEventListener('click',async()=>{
      prepare.disabled=true;prepare.textContent='正在生成本地审阅材料…';
      try{const result=await api('/api/opportunities/prepare',{job_keys:[job.job_key]});const first=result.jobs?.[0];$('discovery-run-status').textContent=first?'已为「'+first.company+' · '+first.title+'」生成本地审阅材料；未发送邮件、未提交申请。':'材料准备完成；未发送邮件、未提交申请。';await refresh();}
      catch(error){$('discovery-run-status').textContent='材料准备未完成：'+error.message;}
      finally{prepare.disabled=!canPrepare;prepare.textContent=application.resume_variant?'重新生成中英审阅材料':'生成中英审阅材料';}
    });
    actions.append(prepare);card.append(actions);
    const needsInquiry=category==='internship'&&qualification.status!=='ineligible'&&(qualification.status==='needs_confirmation'||pay.paid_status==='unknown'||(match.internship_growth||{}).status==='unknown');
    if(needsInquiry){
      const context=qualification.inquiry_context||'已完成本科学业（毕业年限可补充）';
      const questionsZh=[];const questionsEn=[];
      if(qualification.status==='needs_confirmation'){
        questionsZh.push('请问该实习是否接受已毕业人员申请？');
        questionsEn.push('Could you confirm whether applicants who have already graduated are eligible for this internship?');
      }
      if(pay.paid_status==='unknown'){
        questionsZh.push('该岗位是否有薪，薪酬范围及发放周期是什么？');
        questionsEn.push('Is this internship paid, and what are the compensation range and payment schedule?');
      }
      if((match.internship_growth||{}).status==='unknown'){
        questionsZh.push('岗位是否包含明确的带教、培训或可独立负责的项目？');
        questionsEn.push('Does the role include structured mentorship, training, or ownership of a project?');
      }
      const zh='您好，我关注到贵司的「'+(job.title||'该实习岗位')+'」'+(job.requisition_id?'（职位编号 '+job.requisition_id+'）':'')+'。'+context+'。想向您确认：'+questionsZh.join('')+'谢谢！';
      const en='Hello, I am interested in the '+(job.title||'internship role')+' position at '+(job.company||'your company')+(job.requisition_id?' (requisition '+job.requisition_id+')':'')+'. '+context+'. '+questionsEn.join(' ')+' Thank you.';
      const drafts=node('details',undefined,'boss-greeting-draft');drafts.append(node('summary','HR 资格咨询邮件草稿（中英 · 不会发送）'));
      for(const [label,value] of [['中文草稿',zh],['English draft',en]]){const block=node('div');block.append(node('p',value));const copy=node('button','复制'+label,'quiet');copy.type='button';copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(value);notice('草稿已复制到剪贴板；邮件尚未发送。');}catch{$('document-title').textContent=label+'（未发送）';$('document-content').textContent=value;$('document-dialog').showModal();}});block.append(copy);drafts.append(block);}
      card.append(drafts);
    }
    list.append(card);
  });
  if(!rows.length)list.append(node('p',opportunityJobs.length?'当前筛选条件下没有岗位。':'','empty-state'));
}
async function loadOpportunityJobs(){
  try{const result=await api('/api/opportunities');opportunityJobs=Array.isArray(result.jobs)?result.jobs:[];renderOpportunityJobs();}
  catch(error){opportunityJobs=[];renderOpportunityJobs();$('opportunity-status').textContent='本地官方岗位记录暂不可用：'+error.message;}
}
$('career-positioning-panel').addEventListener('toggle',async event=>{
  const panel=event.currentTarget;
  if(!panel.open||panel.dataset.loaded==='true')return;
  const status=$('career-positioning-status'),list=clear('career-positioning');status.textContent='正在读取已校验的本地事实…';
  try{
    const report=await api('/api/career/positioning');panel.dataset.loaded='true';
    status.textContent=report.model_disclosure+' 共列出 '+report.roles.length+' 类岗位。';
    if(report.withheld_project_note)list.append(node('p',report.withheld_project_note+'项目证据未修改。','caption'));
    report.roles.forEach((role,index)=>{
      const section=node('details',undefined,'resource-item'),title=node('summary',(index+1)+' · '+role.title_zh+' / '+role.title_en);
      section.append(title,node('p','优先级 '+role.priority+' · 证据 '+role.evidence_strength+'（直接 '+role.direct_work_evidence_count+' 条 / 可迁移 '+role.transferable_evidence_count+' 条）· 难度：'+role.difficulty),node('p','适合原因：'+role.why));
      const evidence=node('div');evidence.append(node('strong','可追溯经历证据'));
      if(role.evidence.length){const ul=node('ul');role.evidence.forEach(item=>ul.append(node('li',item.excerpt+'（'+item.source_ref+' · '+item.bullet_id+'）')));evidence.append(ul);}else evidence.append(node('p','暂无可安全引用的事实。'));
      section.append(evidence);const gaps=node('div');gaps.append(node('strong','待补能力 / 核实项'));const ul=node('ul');role.gaps.forEach(item=>ul.append(node('li',item)));gaps.append(ul);section.append(gaps);list.append(section);
    });
    (report.limitations||[]).forEach(item=>list.append(node('p',item,'caption')));
  }catch(error){status.textContent='本地职业定位暂不可用：'+error.message;}
});
$('discover-daily-button').addEventListener('click',async()=>{
  const button=$('discover-daily-button'),status=$('discovery-run-status');button.disabled=true;status.textContent='正在读取已支持的官方招聘源；本轮上限 10 个，只发现和核验，不会投递。';
  try{const result=await api('/api/opportunities/discover-daily',{limit:10});await refresh();status.textContent='本轮读取 '+result.sources.length+' 个 ATS 来源，保存 '+result.results_count+' 个岗位；邮件发送 0、申请提交 0。每日后台调度：'+(result.scheduler==='not_configured'?'尚未配置。':'已配置。')+' 覆盖范围仅限已接入来源。';}
  catch(error){status.textContent='岗位发现未完成：'+error.message;}
  finally{button.disabled=false;}
});
$('opportunity-type-filter').addEventListener('change',renderOpportunityJobs);
function bossList(value){return String(value||'').split(/[\n,，;；]+/).map(item=>item.trim()).filter(Boolean);}
function bossNumber(id){const value=$(id).value.trim();return value===''?null:Number(value);}
function bossSettingsFromForm(){
  const settings={
    keywords:bossList($('boss-keywords').value),cities:bossList($('boss-cities').value),company_sizes:bossList($('boss-company-sizes').value),
    excluded_companies:[...(bossState.settings?.excluded_companies||[])],min_salary_k:bossNumber('boss-salary-min'),max_salary_k:bossNumber('boss-salary-max'),
    require_weekends_off:$('boss-weekends').checked,max_open_positions:Number($('boss-open-limit').value),
    company_aliases:bossState.settings?.company_aliases||{},greeting_template:$('boss-greeting').value.trim(),greeting_confirmed:$('boss-greeting-confirmed').checked
  };
  if(!Number.isInteger(settings.max_open_positions)||settings.max_open_positions<0)throw new Error('在招岗位数上限请填 0 或正整数');
  for(const key of ['min_salary_k','max_salary_k'])if(settings[key]!==null&&(!Number.isFinite(settings[key])||settings[key]<=0))throw new Error('薪资范围请填写正数');
  if(settings.min_salary_k!==null&&settings.max_salary_k!==null&&settings.min_salary_k>settings.max_salary_k)throw new Error('月薪下限不能高于上限');
  return settings;
}
function renderBossSettings(settings){
  if(!settings)return;
  $('boss-keywords').value=(settings.keywords||[]).join('，');$('boss-cities').value=(settings.cities||[]).join('，');$('boss-company-sizes').value=(settings.company_sizes||[]).join('，');
  $('boss-salary-min').value=settings.min_salary_k??'';$('boss-salary-max').value=settings.max_salary_k??'';$('boss-open-limit').value=settings.max_open_positions??0;
  $('boss-weekends').checked=Boolean(settings.require_weekends_off);$('boss-greeting').value=settings.greeting_template||'';$('boss-greeting-confirmed').checked=Boolean(settings.greeting_confirmed);
  const list=clear('boss-excluded-list'),blocked=settings.excluded_companies||[];
  list.append(node('span','已屏蔽 '+blocked.length+' 家公司','caption'));
  blocked.slice(0,24).forEach(company=>{const chip=node('span',company,'boss-excluded-chip');const remove=node('button','×');remove.type='button';remove.title='移除 '+company;remove.setAttribute('aria-label','移除屏蔽公司 '+company);remove.addEventListener('click',async()=>{remove.disabled=true;try{await api('/api/boss/settings',{settings:{...bossState.settings,excluded_companies:blocked.filter(name=>name!==company)}});await loadBoss();$('boss-blocked-status').textContent='已从屏蔽名单移除 '+company;}catch(error){$('boss-blocked-status').textContent=error.message;}finally{remove.disabled=false;}});chip.append(remove);list.append(chip);});
  if(blocked.length>24)list.append(node('span','另有 '+(blocked.length-24)+' 家未展示','caption'));
}
const bossLabels={shortlist:'符合已知条件',needs_verification:'待核实',excluded:'明确排除',duplicate:'重复记录'};
function renderBossScreen(screen){
  const root=$('boss-results'),summaryBox=clear('boss-result-summary'),list=clear('boss-result-list');
  if(!screen){root.hidden=true;return;}root.hidden=false;
  const results=Array.isArray(screen.results)?screen.results:[],summary=screen.summary||{};
  $('boss-result-meta').textContent='共 '+results.length+' 条岗位 · 仅为本地筛选';
  for(const status of ['shortlist','needs_verification','excluded','duplicate']){const count=Number(summary[status]??results.filter(item=>item.status===status).length);const chip=node('span',bossLabels[status]+' '+count,'boss-count '+status);summaryBox.append(chip);}
  if(summary.invalid)summaryBox.append(node('span','无法解析 '+summary.invalid,'boss-count needs_verification'));
  if(Array.isArray(screen.errors)&&screen.errors.length){const errorBox=node('details',undefined,'boss-errors');errorBox.append(node('summary','查看 '+screen.errors.length+' 条导入错误'));const errors=node('ul');screen.errors.slice(0,30).forEach(error=>errors.append(node('li','第 '+error.index+' 条：'+error.error)));errorBox.append(errors);list.append(errorBox);}
  for(const status of ['shortlist','needs_verification','excluded','duplicate']){
    const items=results.filter(item=>item.status===status);if(!items.length)continue;
    const group=node('section',undefined,'boss-result-group');group.append(node('h4',bossLabels[status]+' · '+items.length));const cards=node('div',undefined,'boss-card-grid');
    items.forEach(item=>{
      const job=item.job||{},card=node('article',undefined,'boss-card '+status),head=node('div',undefined,'boss-card-head');
      const title=node('h5',job.title||'未命名岗位');head.append(title,node('span',bossLabels[status],'boss-status'));card.append(head,node('p',(job.company||'公司待核验')+' · '+(job.city||'地点待核验'),'boss-company'));
      const facts=['薪资 '+(job.salary||'未知'),'规模 '+(job.company_size||'未知'),'在招数 '+(job.open_positions||'未知')];if(facts.length)card.append(node('p',facts.join(' · '),'boss-facts'));
      const reasons=[...(item.matched_conditions||item.reasons||[]).map(x=>'命中：'+x),...(item.unmet_conditions||[]).map(x=>'未满足：'+x),...(item.unknown_conditions||item.needs_verification||[]).map(x=>'待核实：'+x)];if(reasons.length){const reasonsBox=node('ul',undefined,'boss-reasons');reasons.forEach(reason=>reasonsBox.append(node('li',String(reason))));card.append(reasonsBox);}
      card.append(node('p','来源：'+(item.source||'未知')+' · 最后在线核验：'+(item.last_verified_at||'未知（未核验）'),'caption'));
      const salary=item.salary_details;if(salary)card.append(node('p','薪数：'+(salary.payments??'未知')+' · 年薪范围：'+(salary.annual_min_k===null?'未知':salary.annual_min_k+'–'+salary.annual_max_k+'K'),'caption'));
      if(item.duplicate_of)card.append(node('p','与本次导入的第 '+item.duplicate_of+' 条岗位重复。','caption'));
      const actions=node('div',undefined,'boss-card-actions');if(job.url)actions.append(externalLink('打开岗位链接 ↗',job.url));
      const description=String(job.description||'').trim();const structuredJD=description.length>=120&&/(岗位职责|工作职责|工作内容|职位描述|岗位描述|工作任务)/.test(description)&&/(任职要求|岗位要求|任职资格|资格要求|职位要求|岗位条件)/.test(description);
      const canAuto=structuredJD&&status!=='excluded'&&status!=='duplicate';const reviewOnly=status==='excluded'||status==='duplicate';
      const prepare=node('button',canAuto?'生成此 JD 简历':reviewOnly?'仅查看 JD':'补全 JD 后生成','secondary');prepare.type='button';if(canAuto){prepare.disabled=true;prepare.title='请先核对导入内容与当前岗位页面一致，并勾选完整 JD 确认';const confirm=node('label',undefined,'boss-check boss-jd-confirm');const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.addEventListener('change',()=>{prepare.disabled=!checkbox.checked;});confirm.append(checkbox,node('span','已对照岗位页面核对为完整 JD'));card.append(confirm);}prepare.addEventListener('click',()=>{sessionStorage.setItem('career-studio-jd-prefill',JSON.stringify({jd:structuredJD?description:'',title:job.title||'',company:job.company||'',url:job.url||'',auto_generate:canAuto}));location.assign('/studio');});actions.append(prepare);card.append(actions);
      if(reviewOnly)card.append(node('p','该岗位已排除或重复，不会自动生成材料。','caption'));else if(!structuredJD)card.append(node('p','导入内容缺少完整的岗位职责或任职要求；编辑器将等待你补全 JD。','caption'));
      else{const details=node('details',undefined,'boss-jd');details.append(node('summary','查看导入的 JD 正文'),node('pre',description));card.append(details);}
      if(item.greeting_draft){const greeting=node('div',undefined,'boss-greeting-draft');greeting.append(node('span','招呼语草稿','caption'),node('p',item.greeting_draft));const copy=node('button','复制草稿','quiet');copy.type='button';copy.addEventListener('click',()=>copyBossText(item.greeting_draft,'招呼语草稿'));greeting.append(copy);card.append(greeting);}
      cards.append(card);
    });group.append(cards);list.append(group);
  }
  if(!list.children.length)list.append(node('p','没有可展示的岗位，请检查导入内容和筛选条件。','empty-state'));
}
function renderBoss(state){bossState=state;renderBossSettings(state.settings);renderBossScreen(state.screen);}
async function loadBoss(){try{const state=await api('/api/boss');renderBoss(state);return state;}catch(error){$('boss-settings-status').textContent='BOSS 筛选台暂不可用：'+error.message;return null;}}
async function bossData(textId,fileId){let value=$(textId).value.trim();if(!value&&$(fileId).files[0]){const file=$(fileId).files[0];if(file.size>2*1024*1024)throw new Error('请选择 2 MB 以内的文件');value=(await file.text()).trim();}if(!value)throw new Error('请粘贴内容或选择文件');if(new TextEncoder().encode(value).length>2*1024*1024)throw new Error('导入内容请控制在 2 MB 以内');return value;}
async function copyBossText(value,title){try{await navigator.clipboard.writeText(value);notice('已复制'+title+'，发送前请再次核对。');}catch{$('document-title').textContent=title;$('document-content').textContent=value;$('document-dialog').showModal();}}
function renderReviews(data){const chart=clear('review-chart'),latest=data.reviews[0];dimensions.forEach(name=>chart.append(bar(name,latest&&Number.isInteger(latest.scores[name])?latest.scores[name]:null,5)));if(!latest)chart.append(node('p','保存复盘并填写自评后，图表会显示真实记录。','caption'));else chart.append(node('p',latest.date+' · '+(latest.kind==='practice'?'模拟练习':'真实面试')+' · '+(latest.role||'未指定岗位'),'caption'));const history=clear('review-history');data.reviews.forEach(review=>{const item=node('details',undefined,'surface');item.append(node('summary',review.date+' · '+(review.kind==='practice'?'模拟练习':'真实面试')+' · '+(review.role||review.company||'复盘记录')));const body=node('div',undefined,'review-detail');for(const [key,label] of [['question','问题'],['answer','回答'],['feedback','反馈'],['next_action','下一步改进']]){const p=node('p');p.append(node('strong',label+'：'),document.createTextNode(review[key]||'未记录'));body.append(p);}item.append(body);history.append(item);});if(!data.reviews.length)history.append(node('p','尚未保存复盘。可先练习转行自我介绍、个人贡献、关键取舍与成果证据。','empty-state'));}
async function refresh(){const data=await api('/api/workspace');workspace=data;renderOverview(data);renderAssets(data);renderHistory(data);renderApplications(data);renderPreferences(data);renderReviews(data);$('updated').textContent='资料刷新 '+new Date(data.updated_at).toLocaleTimeString('zh-CN');notice(data.warnings.length?data.warnings.join('；'):'');await loadOpportunityJobs();return data;}
document.querySelectorAll('[data-panel]').forEach(button=>button.addEventListener('click',()=>show(button.dataset.panel)));
document.querySelectorAll('[data-go]').forEach(button=>button.addEventListener('click',()=>show(button.dataset.go)));
window.addEventListener('hashchange',()=>show(location.hash.slice(1)));
  $('refresh').addEventListener('click',async()=>{try{await refresh();await loadBoss();notice('已重新读取案例资料。');}catch(error){notice(error.message);}});
$('include-tests').addEventListener('change',()=>workspace&&renderHistory(workspace));
$('preference-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.currentTarget.querySelector('[type=submit]');button.disabled=true;try{const payload={};for(const key of ['categories','locations','requests'])payload[key]=[...e.currentTarget.querySelectorAll('input[name='+key+']:checked')].map(x=>x.value);await api('/api/workspace/preferences',payload);$('preference-status').textContent='偏好已保存，推荐已按最新选择刷新。';await refresh();}catch(error){$('preference-status').textContent=error.message;}finally{button.disabled=false;}});
$('boss-settings-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.currentTarget.querySelector('[type=submit]'),status=$('boss-settings-status');button.disabled=true;status.textContent='正在保存…';try{await api('/api/boss/settings',{settings:bossSettingsFromForm()});await loadBoss();status.textContent='筛选条件已保存；现有导入岗位已按新条件重新计算。';}catch(error){status.textContent=error.message;}finally{button.disabled=false;}});
$('boss-blocked-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.currentTarget.querySelector('[type=submit]'),status=$('boss-blocked-status');button.disabled=true;status.textContent='正在导入…';try{const data=await bossData('boss-blocked-data','boss-blocked-file');await api('/api/boss/blocked',{data});$('boss-blocked-data').value='';$('boss-blocked-file').value='';await loadBoss();status.textContent='名单已合并；重复公司自动去重。';}catch(error){status.textContent=error.message;}finally{button.disabled=false;}});
$('boss-screen-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.currentTarget.querySelector('[type=submit]'),status=$('boss-screen-status');button.disabled=true;status.textContent='正在筛选…';try{const data=await bossData('boss-job-data','boss-job-file');await api('/api/boss/screen',{data});$('boss-job-data').value='';$('boss-job-file').value='';await loadBoss();status.textContent='筛选完成。请核对岗位原文，再准备对应材料。';}catch(error){status.textContent=error.message;}finally{button.disabled=false;}});
$('ai-recommend').addEventListener('click',async()=>{const button=$('ai-recommend'),status=$('ai-recommend-status'),result=$('ai-recommend-result');button.disabled=true;status.textContent='正在请求 DeepSeek…';result.hidden=true;try{const selected={};for(const key of ['categories','locations','requests'])selected[key]=[...document.querySelectorAll('input[name='+key+']:checked')].map(x=>x.value);const jobs=[...(workspace?.recommendations||[])].slice(0,8).map(x=>({company:x.company,title:x.title,locations:x.locations,evidence:x.evidence,status:x.status}));const prompt='请用中文整理一份求职岗位推荐摘要。只根据以下已确认的偏好和推荐卡片，不补造岗位事实；把“推荐原因”“需要核验的事项”“下一步动作”分成三段，语气简洁。偏好：'+JSON.stringify(selected)+'。推荐卡片：'+JSON.stringify(jobs);const response=await api('/api/ai/recommend',{prompt});result.textContent=response.text;result.hidden=false;status.textContent='摘要已生成；请把它当作辅助说明，岗位链接仍需官网核验。';}catch(error){status.textContent=error.message;}finally{button.disabled=false;}});
$('close-document').addEventListener('click',()=>$('document-dialog').close());
document.querySelectorAll('[data-copy]').forEach(button=>button.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(button.dataset.copy);notice('已复制工作指令，可粘贴到 Codex 继续。');}catch{$('document-title').textContent='工作指令';$('document-content').textContent=button.dataset.copy;$('document-dialog').showModal();}}));
const promptPlaybook={recruiter:'使用 job-search-workflow 的七视角提示库第 1 项。扮演高级招聘人员，对比当前案例事实与这份 JD，提取 10 个核心词、业务问题、直接/相邻/缺失证据，并提出一页简历结构。所有结论引用事实或 JD；不得编造。',achievement:'使用七视角提示库第 2 项。把我的经历拆成问题、职责、行动、取舍、变化、结果和证据，改成结果优先的简历 bullet。没有量化数据时列出应补的口径、基线、周期和来源，不猜数字。',critique:'使用七视角提示库第 3 项。假设你一分钟筛选数百份简历，指出最先吸引和淘汰的内容、泛泛句、疑问及面试追问，并按影响排序写出改哪里、改成什么、为什么。',ats:'使用七视角提示库第 4 项。对比 JD 与简历，列出缺失关键词、无关概念、应突出经历、格式问题，再生成一页优化版。只用已有事实，缺数据写[我需要这个数据]。',trajectory:'使用七视角提示库第 5 项。分析完整职业轨迹的核心能力、成长趋势、优势、缺口和定位，给出适合职位及 30/60/90 天补强计划，区分事实与推断。',coach:'使用七视角提示库第 6 项。根据实际提交版本和 JD 生成 15 个问题，说明考察点、事实、错误和追问；之后一次只问一题，等我回答后按五个维度 1–10 分反馈，不把练习答案写入事实库。',final:'使用七视角提示库第 7 项。从招聘经理角度审计简历、JD 和申请信，给出雇用/淘汰理由、提交前修改和最终决定，再生成一页简历与 7 天计划。每项修改说明战略理由，不得编造。'};
document.querySelectorAll('[data-prompt-key]').forEach(button=>button.addEventListener('click',async()=>{const text=promptPlaybook[button.dataset.promptKey];try{await navigator.clipboard.writeText(text);$('prompt-status').textContent='已复制提示词 '+button.textContent+'；请在同一 JD 对话中粘贴。';}catch{$('document-title').textContent='简历审计提示词';$('document-content').textContent=text;$('document-dialog').showModal();}}));
$('build-portfolio').addEventListener('click',async()=>{const button=$('build-portfolio');button.disabled=true;try{const result=await api('/api/workspace/portfolio',{project_ids:[...document.querySelectorAll('[data-project]:checked')].map(x=>x.value),resume_id:$('portfolio-resume').value});const box=clear('portfolio-result');box.hidden=false;box.append(node('span','作品集与网站草稿已生成 · 尚未发布。 '),link('内容稿',localURL('/files/',result.markdown)),document.createTextNode('　'),link('打开网站预览 ↗',result.preview));await refresh();}catch(error){$('portfolio-result').hidden=false;$('portfolio-result').textContent=error.message;}finally{button.disabled=false;}});
dimensions.forEach(name=>{const label=node('label',name);const select=document.createElement('select');select.dataset.score=name;select.add(new Option('未评分',''));for(let i=1;i<=5;i++)select.add(new Option(String(i),String(i)));label.append(select);$('score-inputs').append(label);});
const today=new Date();document.querySelector('[name=date]').value=[today.getFullYear(),String(today.getMonth()+1).padStart(2,'0'),String(today.getDate()).padStart(2,'0')].join('-');
$('review-form').addEventListener('submit',async event=>{event.preventDefault();if(saving)return;saving=true;const button=event.currentTarget.querySelector('button[type=submit]');button.disabled=true;const values=Object.fromEntries(new FormData(event.currentTarget));values.id=event.currentTarget.dataset.pendingId||(event.currentTarget.dataset.pendingId=crypto.randomUUID());values.scores={};document.querySelectorAll('[data-score]').forEach(s=>{if(s.value)values.scores[s.dataset.score]=Number(s.value);});try{await api('/api/workspace/review',values);$('review-status').textContent='复盘已保存。未改变投递阶段，也未写入职业事实库。';delete $('review-form').dataset.pendingId;for(const name of ['question','answer','feedback','next_action'])document.querySelector('[name='+name+']').value='';await refresh();}catch(error){$('review-status').textContent=error.message;}finally{saving=false;button.disabled=false;}});
(async()=>{try{if(location.protocol==='file:')throw new Error('请通过 http://127.0.0.1:8765 打开工作台，直接打开 HTML 无法连接本地资料');const response=await fetch('/api/bootstrap',{cache:'no-store'});if(!response.ok)throw new Error('无法连接本地服务');token=(await response.json()).token;await refresh();await loadBoss();show(location.hash.slice(1)||'overview',false);}catch(error){notice(error.message+'；请确认本地工作台已启动。');}})();

$('material-form').addEventListener('submit',async e=>{e.preventDefault();const file=$('material-file').files[0],button=e.currentTarget.querySelector('[type=submit]');if(!file)return;if(file.size>6*1024*1024){$('material-status').textContent='请选择 6 MB 以内的文件';return;}button.disabled=true;try{const content=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=()=>reject(new Error('无法读取文件'));r.readAsDataURL(file);});const result=await api('/api/workspace/material',{name:file.name,kind:$('material-kind').value,content});$('material-status').textContent=result.note;await refresh();}catch(error){$('material-status').textContent=error.message;}finally{button.disabled=false;}});

window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;$('install-app').hidden=false;});
$('install-app').addEventListener('click',async()=>{if(!installPrompt)return;installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;$('install-app').hidden=true;});
if('serviceWorker' in navigator && location.protocol==='http:') navigator.serviceWorker.register('/assets/sw.js').catch(()=>{});

window.addEventListener('popstate',()=>show(location.hash.slice(1)||'overview'));
