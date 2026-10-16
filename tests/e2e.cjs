/* Real headless browser tests. Runs only temporary synthetic/empty local cases. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const ROOT = path.resolve(__dirname, '..');
const OUT = process.env.E2E_OUT_DIR || path.join(ROOT, 'docs/ui-restoration/evidence');
fs.mkdirSync(OUT, { recursive: true });
const checks = [], processes = [];
function start(empty=false) {
  return new Promise((resolve,reject)=>{
    const child=spawn(process.env.PYTHON_BIN||'python3',['-B','scripts/demo_server.py','--port','0',...(empty?['--empty']:[])],{cwd:ROOT});processes.push(child);
    let output='';child.stdout.on('data',d=>{output+=d;const match=output.match(/http:\/\/127\.0\.0\.1:(\d+)/);if(match)resolve('http://127.0.0.1:'+match[1]);});
    child.stderr.on('data',d=>fs.appendFileSync(path.join(OUT,'e2e-server.log'),d));child.on('exit',code=>{if(!output.includes('http://'))reject(new Error('Local server failed: '+code));});
  });
}
async function check(name, fn){const result=await fn();const status=result?.status||'passed';checks.push({name,status,...(result?.reason?{reason:result.reason}:{})});process.stdout.write(status.toUpperCase()+' '+name+(result?.reason?' — '+result.reason:'')+'\n');}
async function screenshot(page,name,fullPage=false){await page.screenshot({path:path.join(OUT,name+'.png'),fullPage,animations:'disabled'});}
async function noOverflow(page){assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'horizontal overflow');}
(async()=>{
  let browser;
  try{
    const base=await start(),empty=await start(true);
    browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_EXECUTABLE||chromium.executablePath()});
    const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];
    page.on('pageerror',e=>errors.push(String(e)));
    await check('public preview restores classic landing and labels synthetic scope',async()=>{
      await page.goto(base+'/demo');await page.getByRole('heading',{name:/同一份经历/}).waitFor();
      assert.deepEqual(await page.locator('.site-header nav a').allTextContents(),['工作流程','岗位示例','BOSS 辅助','使用方式']);
      assert((await page.locator('.demo-boundary').innerText()).includes('不连接 BOSS'));
      assert.equal(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor),'rgb(245, 245, 247)');
      await noOverflow(page);await screenshot(page,'public-desktop');
    });
    await check('five job seeker scenarios expose start result and next step',async()=>{
      await page.getByText('按你的情况开始：五种使用路径',{exact:true}).click();
      for(const scenario of ['new','complete','transition','multi','single']){
        await page.getByLabel('体验一种使用场景').selectOption(scenario);
        assert((await page.locator('#next-copy').innerText()).length>10);
        await page.locator('#next-action').click();
        assert.equal(await page.locator(':focus').getAttribute('tabindex'),'-1');
        assert.equal(await page.locator('#next-action').getAttribute('href'),scenario==='new'?'#use-title':'#preview-title');
      }
      await page.getByRole('button',{name:'体验已有合成档案',exact:true}).click();assert.equal(await page.getByLabel('体验一种使用场景').inputValue(),'complete');
    });
    await check('public role switching and review are synthetic only',async()=>{
      await page.getByRole('button',{name:'产品运营',exact:true}).click();
      assert.equal(await page.locator('#demo-title').innerText(),'产品运营');await page.getByRole('button',{name:'查看审阅状态'}).click();
      assert((await page.locator('#demo-status').innerText()).includes('没有真实投递'));
    });
    await check('empty local case begins with intake and recovers from invalid material',async()=>{
      await page.goto(empty);await page.locator('#next-action').getByText('上传简历',{exact:true}).waitFor();await page.locator('#next-action').click();
      await page.locator('#material-file').setInputFiles({name:'empty.txt',mimeType:'text/plain',buffer:Buffer.from('too short')});await page.getByRole('button',{name:'导入并提取材料',exact:true}).click();
      await page.locator('#material-status').filter({hasText:'未读取到足够文字'}).waitFor();
      await page.locator('#material-file').setInputFiles({name:'synthetic.txt',mimeType:'text/plain',buffer:Buffer.from('【合成测试】本人协助组织社区课程活动，整理参与者反馈，时间、数量与来源需核对。')});await page.getByRole('button',{name:'导入并提取材料',exact:true}).click();
      await page.locator('#material-status').filter({hasText:'尚未合并事实'}).waitFor();await page.getByRole('button',{name:'总览',exact:true}).click();
      await page.locator('#next-title').filter({hasText:'先核对已导入'}).waitFor();
    });
    await check('complete local case offers direct JD and goal preferences',async()=>{
      await page.goto(base);await page.locator('#next-action').filter({hasText:'分析新岗位'}).waitFor();
      await page.getByRole('button',{name:'投递进度',exact:true}).click();await page.locator('#preference-form input[value="产品运营"]').check();await page.getByRole('button',{name:'保存偏好并刷新推荐'}).click();
      await page.locator('#preference-status').filter({hasText:'偏好已保存'}).waitFor();await page.getByRole('button',{name:'总览',exact:true}).click();
      await page.getByText('当前目标、档案与最近进度',{exact:true}).click();assert((await page.locator('#current-target').innerText()).includes('产品运营'));await page.getByText('当前目标、档案与最近进度',{exact:true}).click();
      await page.evaluate(()=>window.scrollTo(0,0));await screenshot(page,'local-desktop');
    });
    await check('classic six-tab navigation retains projects interview site and lazy JD editor',async()=>{
      assert.deepEqual(await page.locator('.navigation button').allTextContents(),['总览','素材与作品集','JD 简历','投递进度','面试复盘','个人网站']);
      for(const [label,panel] of [['素材与作品集','assets'],['JD 简历','resume'],['投递进度','applications'],['面试复盘','interview'],['个人网站','website'],['总览','overview']]){
        await page.getByRole('button',{name:label,exact:true}).click();assert.equal(await page.locator(`[data-section="${panel}"]`).isVisible(),true);assert.equal(await page.locator('.navigation [aria-current=page]').innerText(),label);await noOverflow(page);
      }
      assert.equal(await page.locator('#studio-frame').getAttribute('src'),'/studio');assert.equal(await page.locator('#project-gallery .project').count(),3);
      assert.equal(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor),'rgb(245, 245, 247)');
      assert.equal(await page.locator('.hero h1').evaluate(el=>getComputedStyle(el).fontSize),'68px');
      await page.goBack();assert.equal(await page.locator('[data-section="website"]').isVisible(),true);await page.goForward();assert.equal(await page.locator('[data-section="overview"]').isVisible(),true);
    });
    await check('JD requirements and all evidence are inspectable',async()=>{
      await page.goto(base+'/studio');await page.getByRole('button',{name:'AI 知识库',exact:true}).waitFor();await screenshot(page,'jd-desktop');
      const columns=await page.locator('.workspace').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length);assert.equal(columns,2);
      await page.getByRole('button',{name:'AI 知识库',exact:true}).click();await page.getByRole('button',{name:'先分析要求与证据'}).click();
      await page.locator('#status').filter({hasText:'分析完成'}).waitFor();assert(await page.locator('.requirement-row').count()>0);assert.equal(await page.locator(':focus').getAttribute('id'),'review-heading');
      await page.getByText('全部候选证据与选择理由',{exact:true}).click();assert.equal(await page.locator('.selection-row').count(),15);await page.getByRole('button',{name:'查看原始事实库',exact:true}).first().click();await page.locator('#source-dialog').waitFor({state:'visible'});assert((await page.locator('#source-text').innerText()).length>100);await page.getByRole('button',{name:'关闭原文'}).click();
      assert((await page.locator('#evidence-review #priority-project').count())===1);
      await page.getByLabel('最优先项目').selectOption('project-archive');await page.getByRole('button',{name:'更新选材预览'}).click();await page.locator('#status').filter({hasText:'分析完成'}).waitFor();
    });
    await check('generation retains review state and reuses exact repeat',async()=>{
      await page.getByRole('button',{name:'生成独立简历版本'}).click();await page.locator('#status').filter({hasText:'材料已生成'}).waitFor({timeout:20000});
      assert((await page.locator('#result-caption').innerText()).includes('未投递'));
      const href=await page.getByRole('link',{name:'下载 PDF'}).getAttribute('href');await page.getByRole('button',{name:'生成独立简历版本'}).click();await page.locator('#status').filter({hasText:'材料已生成'}).waitFor({timeout:20000});
      assert.equal(await page.getByRole('link',{name:'下载 PDF'}).getAttribute('href'),href);await noOverflow(page);await page.locator('#result').scrollIntoViewIfNeeded();await screenshot(page,'jd-generated-desktop');
    });
    await check('numbered JD analysis and seven-day plan remain available',async()=>{
      await page.getByRole('button',{name:'分析逐项符合度与 7 天补齐计划'}).click();await page.locator('#status.error').filter({hasText:'请保留 JD'}).waitFor();
      await page.getByLabel('岗位 JD 正文').fill('【合成测试】用户运营\n职位描述\n1、维护客户关系，整理用户反馈与问题记录。\n2、建立知识库内容更新流程。\n职位要求\n1、具备用户沟通和文档整理能力。\n2、熟练使用 SQL。');
      await page.getByRole('button',{name:'分析逐项符合度与 7 天补齐计划'}).click();await page.locator('#analysis').waitFor({state:'visible'});
      assert.equal(await page.locator('.analysis-day').count(),7);assert(await page.locator('.analysis-row').count()>0);
    });
    await check('manual direction cannot bypass unsupported role',async()=>{
      await page.getByLabel('岗位名称').fill('机器学习工程师');await page.getByLabel('岗位 JD 正文').fill('【合成测试】岗位职责：独立负责分布式模型训练与PyTorch训练框架，设计生产级模型架构。任职要求：计算机硕士，五年算法研究经验。');
      await page.getByLabel('岗位类型').selectOption('product-operations');await page.getByRole('button',{name:'生成独立简历版本'}).click();await page.locator('#status').filter({hasText:'匹配报告已生成'}).waitFor();assert(await page.locator('#no-pdf').isVisible());
    });
    await check('board has six states and generated material never becomes submitted',async()=>{
      await page.goto(base+'/#applications');await page.locator('#application-board .board-column').first().waitFor();assert.equal(await page.locator('#application-board .board-column').count(),6);
      assert.equal(await page.locator('#confirmed-count').innerText(),'0');
    });
    await check('local positioning cites evidence and daily discovery stays bounded',async()=>{
      await page.goto(base+'/#applications');
      await page.locator('#career-positioning-panel summary').click();
      await page.locator('#career-positioning-status').filter({hasText:'未向外部模型发送'}).waitFor();
      assert((await page.locator('#career-positioning').innerText()).includes('AI 运营'));
      assert((await page.locator('#career-positioning').innerText()).includes('career-evidence-bank.md'));
      await page.route('**/api/opportunities/discover-daily',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
        mode:'discovery-only',results_count:1,sources:[{tenant:'synthetic'}],scheduler:'not_configured',
        external_actions:{emails_sent:0,applications_submitted:0}})}));
      await page.getByRole('button',{name:'搜索官方岗位（最多 10）'}).click();
      await page.locator('#discovery-run-status').filter({hasText:'保存 1 个岗位'}).waitFor();
      assert((await page.locator('#discovery-run-status').innerText()).includes('申请提交 0'));
    });
    await check('official opportunity panel filters internship, explains eligibility and opens JD Studio',async()=>{
      const syntheticJD='Paid internship. Responsibilities: review AI content quality and label examples. Requirements: strong written communication. The role includes mentorship and training.';
      await page.route('**/api/opportunities',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({jobs:[{
        job_key:'opportunity-aaaaaaaaaaaaaaaaaaaa',company:'Synthetic Global',title:'AI Content Intern',url:'https://jobs.lever.co/weloglobal/11111111-1111-1111-1111-111111111111',
        jd:syntheticJD,location:'Shanghai',employment_type:'Internship',posted_date_text:'未知',requisition_id:'SYN-01',
        verification:{status:'verified_open',verified_at:'2026-10-16T00:00:00+00:00'},
        match:{grade:'B',grade_reasons:['薪资范围待核实。'],warnings:['官方 JD 未说明是否接受已毕业人员；需向招聘方确认。'],hard_reasons:[],
          target_priority:'P0',target_label:'AI Content Quality',employment_category:'internship',
          internship_qualification:{status:'needs_confirmation',reason:'官方 JD 未说明是否接受已毕业、非在校人员；需向招聘方确认。',inquiry_context:'已完成本科学业（合成样例）'},
          internship_growth:{status:'supported',reason:'JD 明确提到培训'},work_mode:{status:'onsite',label:'现场办公',reason:'来源明确写明上海现场办公。'},
          posted_compensation:{paid_status:'paid',published:'有薪（具体金额未披露）'},salary:{floor_text:'示例薪资偏好',status:'unknown'},requirements:[]}
      }],mode:'discovery-only'})}));
      await page.goto(base+'/#applications');
      const list=page.locator('#opportunity-list');await list.getByText('AI Content Intern').waitFor();
      assert((await list.innerText()).includes('毕业资格待确认'));assert((await list.innerText()).includes('示例薪资偏好'));
      await page.locator('#opportunity-type-filter').selectOption('full_time');assert.equal(await list.locator('.recommendation-card').count(),0);
      await page.locator('#opportunity-type-filter').selectOption('internship');assert.equal(await list.locator('.recommendation-card').count(),1);
      await list.locator('details summary').first().click();assert((await list.innerText()).includes('官方 JD 未说明是否接受已毕业'));
      await list.getByRole('button',{name:'复制中文草稿'}).waitFor();assert((await list.innerText()).includes('不会发送'));
      await screenshot(page,'internship-screen-desktop');await page.setViewportSize({width:390,height:844});await noOverflow(page);await screenshot(page,'internship-screen-mobile');await page.setViewportSize({width:1440,height:1000});
      await list.getByRole('button',{name:'送入 JD Studio'}).click();await page.waitForURL(/\/studio$/);
      assert.equal(await page.locator('#jd').inputValue(),syntheticJD);
      await page.unroute('**/api/opportunities');
    });
    await check('BOSS screening refreshes saved data and shows unknown verification',async()=>{
      const row={url:'https://www.zhipin.com/job_detail/Ab1234567890.html',company:'合成公司',title:'用户运营',city:'上海',salary:'10-15K·13薪',description:'岗位职责：维护用户关系，整理反馈与活动记录。任职要求：有沟通与文档整理能力。'};
      await page.locator('#boss-job-data').fill(JSON.stringify([row]));await page.getByRole('button',{name:'筛选岗位',exact:true}).click();
      await page.locator('#boss-result-list .boss-card').first().waitFor();assert((await page.locator('#boss-result-list').innerText()).includes('最后在线核验：未知'));
      await page.locator('#boss-salary-min').fill('20');await page.getByRole('button',{name:'保存筛选条件',exact:true}).click();
      await page.locator('#boss-result-list .boss-card.excluded').waitFor();assert((await page.locator('#boss-result-list').innerText()).includes('明确排除'));
    });
    await check('mobile responsive layout and keyboard focus',async()=>{
      await page.setViewportSize({width:390,height:844});await page.goto(base+'/demo');await noOverflow(page);await screenshot(page,'public-mobile');
      await page.keyboard.press('Tab');assert.equal(await page.locator(':focus').innerText(),'跳到主要内容');
      await page.goto(base);await page.locator('#next-title').filter({hasText:'分析一个新岗位'}).waitFor();await noOverflow(page);await screenshot(page,'local-mobile');
      await page.goto(base+'/studio');await page.getByRole('button',{name:'用户运营',exact:true}).waitFor();await noOverflow(page);await screenshot(page,'jd-mobile');
      await page.getByRole('button',{name:'用户运营',exact:true}).click();await page.getByRole('button',{name:'先分析要求与证据'}).click();await page.locator('#status').filter({hasText:'分析完成'}).waitFor();await noOverflow(page);await screenshot(page,'jd-evidence-mobile');
    });
    await check('all local surfaces fit phone tablet and desktop widths',async()=>{
      for(const width of [360,768,1024,1440]){
        await page.setViewportSize({width,height:900});await page.goto(base);await page.locator('#next-action').filter({hasText:'分析新岗位'}).waitFor();
        for(const [label,panel] of [['总览','overview'],['素材与作品集','assets'],['JD 简历','resume'],['投递进度','applications'],['面试复盘','interview'],['个人网站','website']]){
          await page.getByRole('button',{name:label,exact:true}).click();await noOverflow(page);
          if([360,1440].includes(width))await screenshot(page,panel+'-'+width);
        }
        await page.goto(base+'/studio');await page.locator('#generate:not([disabled])').waitFor();await noOverflow(page);
      }
    });
    await check('service worker refreshes old shell and caches no personal preview',async()=>{
      const isolated=await browser.newContext(),fresh=await isolated.newPage();
      try{
        await fresh.goto(base+'/studio');await fresh.evaluate(async()=>{const cache=await caches.open('career-studio-shell-v2');await cache.put('/portfolio-preview/synthetic-placeholder',new Response('synthetic only'));});
        await fresh.goto(base);await fresh.locator('#next-action').filter({hasText:'分析新岗位'}).waitFor();
        const registration=await fresh.evaluate(async()=>{try{await navigator.serviceWorker.register('/assets/sw.js');return {ok:true};}catch(error){return {ok:false,name:error.name,message:error.message};}});
        if(!registration.ok){
          assert.equal(registration.name,'SecurityError');assert(/Content Security Policy|scriptURL/i.test(registration.message));
          return {status:'blocked',reason:'Existing nonce-only CSP blocks worker registration; server security unchanged. Offline caching is not claimed as passed.'};
        }
        await fresh.evaluate(()=>Promise.race([navigator.serviceWorker.ready,new Promise((_,reject)=>setTimeout(()=>reject(new Error('Service worker activation timeout')),10000))]));
        await fresh.waitForFunction(async()=>!(await caches.keys()).includes('career-studio-shell-v2'));
        const keys=await fresh.evaluate(async()=>{const out=[];for(const key of await caches.keys()){const cache=await caches.open(key);for(const request of await cache.keys())out.push(new URL(request.url).pathname);}return out;});
        assert.equal(keys.length,4);assert(keys.every(p=>['/','/assets/career-workspace.css','/assets/career-workspace.js','/assets/manifest.webmanifest'].includes(p)));assert(!keys.some(p=>p.startsWith('/portfolio-preview/')));
      }finally{await isolated.close();}
    });
    await check('input keyboard focus meets declared ring',async()=>{await page.goto(base+'/studio');await page.getByLabel('岗位 JD 正文').focus();const outline=await page.getByLabel('岗位 JD 正文').evaluate(el=>getComputedStyle(el).outlineWidth);assert.equal(outline,'3px');});
    await check('no browser JavaScript errors',async()=>assert.deepEqual(errors,[]));
    fs.writeFileSync(path.join(OUT,'e2e-results.json'),JSON.stringify({suite:'Classic UI with V2 functions — real Chromium E2E',checks,total:checks.length,passed:checks.filter(c=>c.status==='passed').length,blocked:checks.filter(c=>c.status==='blocked').length,synthetic_only:true},null,2)+'\n');
  }catch(error){checks.push({name:'failure',status:'failed',error:String(error.stack||error)});fs.writeFileSync(path.join(OUT,'e2e-results.json'),JSON.stringify({checks},null,2));process.stderr.write(String(error.stack||error)+'\n');process.exitCode=1;}
  finally{if(browser)await browser.close();for(const child of processes)child.kill('SIGINT');}
})();
