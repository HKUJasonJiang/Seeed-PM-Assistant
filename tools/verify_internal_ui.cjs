/* Run against a new temporary profile. Source documents stay local and model calls are blocked. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {spawn,spawnSync}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const sourceFolder=process.env.SEEED_TEST_INTERNAL_SOURCE;
if(!sourceFolder)throw Error('SEEED_TEST_INTERNAL_SOURCE must name the explicitly authorized local source folder.');

async function ready(server){
  return new Promise((resolve,reject)=>{
    let log='';const timeout=setTimeout(()=>reject(Error('Temporary service startup timed out')),30000);
    server.stdout.on('data',chunk=>{log+=chunk;const url=log.match(/http:\/\/127\.0\.0\.1:\d+/)?.[0];if(url){clearTimeout(timeout);resolve(url+'/');}});
    server.once('exit',code=>{clearTimeout(timeout);reject(Error('Service exited '+code));});
    server.stderr.on('data',chunk=>process.stderr.write(chunk));
  });
}
async function run(browser,origin,language,width){
  const page=await browser.newPage({viewport:{width,height:920}}),errors=[],assessments=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{
    const u=new URL(route.request().url());
    if(u.origin!==origin.slice(0,-1))return route.abort();
    if(/\/api\/(?:ai|chats\/[^/]+\/send)$/.test(u.pathname)){errors.push('Unexpected model request');return route.abort();}
    if(u.pathname==='/api/internal/assess')assessments.push(route.request().postDataJSON());
    return route.continue();
  });
  const api=async(route,body)=>{
    const state=await (await page.request.get(origin+'api/state')).json();
    const response=body===undefined?await page.request.get(origin+route):await page.request.post(origin+route,{headers:{Origin:origin.slice(0,-1),'X-CSRF-Token':state.csrf},data:body});
    assert(response.ok(),route+' '+response.status());return response.json();
  };
  try{
    await api('api/settings',{language:language==='en'?'en':'zh'});
    await page.goto(origin+'#developer');await page.locator('[data-wb-id="internal"]').click();
    await page.locator('#internal-path').fill(sourceFolder);await page.locator('#internal-import button').click();
    await page.locator('.internal-status').waitFor();
    const profile=await api('api/state'),privateData=await api('api/internal');
    assert(privateData.summary.documents>0);
    assert(await page.locator('.internal-documents li').count()===privateData.summary.documents);
    await page.locator('#internal-query').fill('SSD');assert(await page.locator('#internal-results .internal-record').count()>0);
    const source=page.locator('#internal-results [data-internal-source]').first();
    await source.click();await page.locator('#internal-source-content pre').waitFor();
    assert((await page.locator('#internal-source-content pre').innerText()).length>0);
    await page.locator('#internal-source-dialog').press('Escape');assert(!await page.locator('#internal-source-dialog').isVisible());
    await page.evaluate(id=>InternalUI.openSource(id,'','previous-version'),privateData.records[0].sourceId);
    await page.locator('#internal-source-content .internal-error').waitFor();await page.locator('[data-internal-close]').click();
    const localOnly=Object.values(profile.internalProducts).find(p=>p.internalOnly&&p.name!==p.sku);
    assert(localOnly,'Imported private product exists');
    await page.locator('[data-view="assistant"]').click();
    await page.locator('#asktext').fill(localOnly.name);await page.locator('#ask button').click();
    await page.locator('.hero-product').filter({hasText:localOnly.sku}).waitFor();
    assert(await page.locator('.selected .product-url').count()===0);
    assert((await page.locator('.internal-product-records').count())>0);
    const eol=Object.values(profile.internalProducts).find(p=>p.eol&&!p.internalOnly);
    assert(eol);
    await page.locator('#asktext').fill(eol.sku);await page.locator('#ask button').click();
    await page.locator('.hero-product').filter({hasText:eol.sku}).waitFor();
    assert.equal(await page.locator('.hero-product h2 .internal-eol-text').count(),1);
    assert.equal(await page.locator('.item-sku .internal-eol-text').count(),1);
    assert(await page.locator('.internal-eol-notice [data-internal-source]').count()>0);

    const host='114110247';
    if(!profile.customizableSkus.includes(host))await api('api/product',{sku:host,customConfirmed:true});
    await page.goto(origin+'#product='+host);await page.locator('.selected [data-wb-action="custom-for"]').click();
    await page.locator('[data-wb-action="new-from-sku"][data-wb-sku="'+host+'"]').click();
    await page.locator('#wb-project-title').fill('Internal UI test '+language);
    await page.locator('#wb-project-description').fill(language==='en'?'Upgrade SSD to 2TB':'SSD升级为2TB');
    await page.locator('[data-internal-material="114993467"][data-internal-operation="replace"]').waitFor();
    assert.match(await page.locator('#internal-project-review').innerText(),/128\s?GB/i);
    await page.locator('[data-internal-material="114993467"][data-internal-operation="replace"]').click();
    await page.locator('#wb-project-form .wb-materials').filter({hasText:'114993467'}).waitFor();
    await page.locator('[data-wb-material-quantity="0"]').fill('2');
    await page.locator('[data-internal-material="114993467"][data-internal-operation="replace"]').click();
    assert.equal(await page.locator('[data-wb-material-quantity="0"]').inputValue(),'2');
    await page.locator('#wb-project-form button[type="submit"]').click();
    await page.waitForFunction(()=>!document.querySelector('#wb-project-form'));
    const saved=(await api('api/state')).projects.find(p=>p.title==='Internal UI test '+language);
    assert(saved);assert.deepEqual(saved.materials.map(({sku,hostSku,action,quantity})=>({sku,hostSku,action,quantity})),[{sku:'114993467',hostSku:host,action:'replace',quantity:2}]);
    await page.reload();await page.locator('[data-wb-action="edit-project"][data-wb-id="'+saved.id+'"]').click();
    assert.match(await page.locator('#wb-project-form .wb-materials').innerText(),/114993467/);
    await page.locator('[data-wb-action="material-remove"]').click();
    await page.locator('#wb-project-description').fill(language==='en'?'Add a SATA data drive and retain the current system drive':'新增SATA数据盘，保留原系统盘');
    await page.waitForFunction(()=>{const p=document.querySelector('#internal-project-review');return p&&!p.hidden&&!/正在|Checking/.test(p.textContent)&&!p.querySelector('[data-internal-material]');});
    assert(!await page.locator('[data-internal-material]').count());
    assert(assessments.every(body=>body.skus.length===1&&body.skus[0]===host));
    const dualHost='100090853';
    if(!profile.customizableSkus.includes(dualHost))await api('api/product',{sku:dualHost,customConfirmed:true});
    await page.goto(origin+'#product='+dualHost);await page.reload();await page.locator('.selected [data-wb-action="custom-for"]').click();
    await page.locator('[data-wb-action="new-from-sku"][data-wb-sku="'+dualHost+'"]').click();
    await page.locator('#wb-project-description').fill(language==='en'?'drive 1 replace with 1TB industrial grade, drive 2 retain 256GB':'盘1换1TB工业级，盘2保留256GB');
    await page.waitForFunction(()=>{const p=document.querySelector('#internal-project-review');return p&&!p.hidden&&!/正在|Checking/.test(p.textContent);});
    assert(assessments.some(body=>body.skus.length===1&&body.skus[0]===dualHost));

    const internalSource=privateData.records.find(r=>r.sourceId),chatId='fixture-chat';
    const turn={id:'fixture-turn',query:'Check source',answer:'Locally supplied test answer',sku:host,sources:[{id:'I1',kind:'internal',sourceId:internalSource.sourceId,title:'Test internal source',location:internalSource.location,version:internalSource.version}]};
    const chat={id:chatId,title:'Source test',createdAt:new Date().toISOString(),updatedAt:new Date().toISOString(),turnCount:1,lastSku:host,turns:[turn]};
    await page.route('**/api/chats',route=>route.fulfill({json:{chats:[chat]}}));
    await page.route('**/api/chats/'+chatId,route=>route.fulfill({json:{chat}}));
    await page.locator('[data-chat-action="toggle"]').click();await page.locator('.sc-sources summary').click();
    const cited=page.locator('[data-chat-action="internal"]');await cited.waitFor();
    assert.match(await cited.locator('..').innerText(),language==='en'?/Internal document/:/内部资料/);
    await cited.click();await page.locator('#internal-source-content pre').waitFor();await page.locator('[data-internal-close]').click();
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    assert.deepEqual(errors,[]);console.log('Passed internal UI '+language+' '+width+'px');
  }finally{await page.close();}
}
(async()=>{
  const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'seeed-internal-ui-'));
  const server=spawn(path.join(root,'.venv','Scripts','python.exe'),['-m','backend.server','--port','0','--data-dir',temporary],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let browser;
  try{
    const origin=await ready(server),edge=path.join(process.env['ProgramFiles(x86)']||'','Microsoft/Edge/Application/msedge.exe');
    browser=await chromium.launch({headless:true,executablePath:fs.existsSync(edge)?edge:undefined});
    await run(browser,origin,'zh-CN',1440);await run(browser,origin,'en',390);
    const file=await browser.newPage(),requests=[];
    file.on('request',r=>{if(r.url().includes('/api/internal'))requests.push(r.url());});
    await file.goto(pathToFileURL(path.join(root,'index.html')).href);await file.locator('.hero-product').waitFor();
    assert.equal(await file.locator('.internal-eol-badge').count(),0);assert.equal(requests.length,0);await file.close();
  }finally{
    if(browser)await browser.close();server.kill();await new Promise(resolve=>server.once('exit',resolve));
    const resolved=path.resolve(temporary);if(path.dirname(resolved)!==path.resolve(os.tmpdir()))throw Error('Unexpected temporary path');
    if(process.platform==='win32'){
      const command="$taskPath=(Resolve-Path -LiteralPath $env:SEEED_UI_TEMP).Path; if((Split-Path -Parent $taskPath) -ne $env:TEMP -or (Split-Path -Leaf $taskPath) -notlike 'seeed-internal-ui-*'){throw 'Unexpected task directory'}; Remove-Item -LiteralPath $taskPath -Recurse -Force -ErrorAction Stop";
      const result=spawnSync('powershell.exe',['-NoProfile','-Command',command],{windowsHide:true,env:{...process.env,SEEED_UI_TEMP:resolved},encoding:'utf8'});if(result.status)throw Error('Cleanup failed '+result.stderr);
    }else fs.rmSync(resolved,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
