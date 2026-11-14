/* Local performance sample with a temporary profile. It never reads the user's workspace profile. */
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {spawn,spawnSync}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const output=process.argv[2];
const samples=[];

async function ready(server){
  return new Promise((resolve,reject)=>{
    let log='';
    const timeout=setTimeout(()=>reject(Error('Temporary service did not become ready.')),30000);
    server.stdout.on('data',chunk=>{
      log+=chunk;const url=log.match(/http:\/\/127\.0\.0\.1:\d+/)?.[0];
      if(url){clearTimeout(timeout);resolve(url+'/');}
    });
    server.once('exit',code=>{clearTimeout(timeout);reject(Error('Service exited '+code));});
    server.stderr.on('data',chunk=>process.stderr.write(chunk));
  });
}
async function sample(browser,url,label,width){
  const page=await browser.newPage({viewport:{width,height:900},bypassCSP:true});
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>{
    window.__timings={search:[],longTasks:[]};
    new PerformanceObserver(list=>{for(const e of list.getEntries())window.__timings.longTasks.push(Math.round(e.duration));}).observe({type:'longtask',buffered:true});
  });
  await page.route('**/*',async route=>{
    const u=new URL(route.request().url());
    if(!['127.0.0.1',''].includes(u.hostname))return route.abort();
    if(u.pathname.endsWith('/search.js')){
      return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(root,'search.js'),'utf8')+'\n{const original=createSearch;createSearch=function(...args){const t=performance.now();const value=original(...args);window.__timings.search.push(performance.now()-t);return value;};}'});
    }
    return route.continue();
  });
  try{
    await page.goto(url+'#product=113991334&tab=accessories');
    await page.locator('.hero-product').waitFor();
    const initial=await page.evaluate(()=>({readyMs:performance.now(),domNodes:document.querySelectorAll('*').length,...window.__timings}));
    const catalogText=fs.readFileSync(path.join(root,'data/catalog.js'),'utf8');
    const catalogue=await page.evaluate(source=>{
      const start=performance.now(),compile=new Function(source),compiled=performance.now();
      const saved=window.SEEED_CATALOG;compile();const executed=performance.now();window.SEEED_CATALOG=saved;
      return {compileMs:compiled-start,executeMs:executed-compiled,products:saved.products.length};
    },catalogText);
    const input=async(id,values)=>page.evaluate(async({id,values})=>{
      const times=[];
      for(const value of values){const field=document.getElementById(id),start=performance.now();field.value=value;field.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:value}));times.push(performance.now()-start);await new Promise(requestAnimationFrame);}
      return times;
    },{id,values});
    const accessories=await input('accfilter',['w','wi','wif','wifi','','EU868','SPI','']);
    await page.locator('[data-view="catalog"]').click();
    const directory=await input('cattext',['g','gr','gro','grov','grove','','r','re','rec','recomputer','']);
    const queries=await page.evaluate(()=>{
      const search=createSearch(window.SEEED_CATALOG);
      return ['J4012','R1100 EU868','XIAO ESP32S3 Sense','工业网关 RS485','wifi'].map(query=>{const t=performance.now(),r=search.lookup(query);search.alternatives(r.primary,query,r.needs);return {query,ms:performance.now()-t};});
    });
    let favoriteMs=null;
    if(label.startsWith('full')){
      await page.locator('[data-view="assistant"]').click();
      const star=page.locator('.selected [data-wb-action="star"]'),was=await star.getAttribute('aria-pressed');
      const start=Date.now();await star.click();
      await page.locator('.selected [data-wb-action="star"][aria-pressed="'+(was==='true'?'false':'true')+'"]').waitFor();favoriteMs=Date.now()-start;
    }
    const final=await page.evaluate(()=>({...window.__timings,overflow:document.documentElement.scrollWidth>innerWidth+1}));
    const row={label,width,initial,catalogue,accessories,directory,queries,favoriteMs,final,errors};samples.push(row);console.log(JSON.stringify(row));
  }finally{await page.close();}
}
(async()=>{
  const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'seeed-performance-'));
  const python=path.join(root,'.venv','Scripts','python.exe');
  const server=spawn(python,['-m','backend.server','--port','0','--data-dir',temporary],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let browser;
  try{
    const url=await ready(server);
    if(process.env.SEEED_TEST_INTERNAL_SOURCE){
      const state=await (await fetch(url+'api/state')).json();
      const response=await fetch(url+'api/internal',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf,Origin:url.slice(0,-1)},body:JSON.stringify({action:'import',path:process.env.SEEED_TEST_INTERNAL_SOURCE})});
      const imported=await response.json();if(!response.ok)throw Error(imported.error||'Import failed');
      console.log(JSON.stringify({internalImport:{documents:imported.summary.documents,records:imported.summary.records,matched:imported.summary.matched,unmatched:imported.summary.unmatched,eol:imported.summary.eol}}));
    }
    const edge=path.join(process.env['ProgramFiles(x86)']||'','Microsoft/Edge/Application/msedge.exe');
    browser=await chromium.launch({headless:true,executablePath:fs.existsSync(edge)?edge:undefined});
    await sample(browser,url,'full-desktop',1440);
    await sample(browser,url,'full-narrow',390);
    await sample(browser,pathToFileURL(path.join(root,'index.html')).href,'file-desktop',1440);
    await sample(browser,pathToFileURL(path.join(root,'index.html')).href+'?lang=en','file-narrow',390);
    if(output)fs.writeFileSync(output,JSON.stringify(samples,null,2));
  }finally{
    if(browser)await browser.close();server.kill();await new Promise(resolve=>server.once('exit',resolve));
    const resolved=path.resolve(temporary),parent=path.resolve(os.tmpdir());
    if(path.dirname(resolved)!==parent||!path.basename(resolved).startsWith('seeed-performance-'))throw Error('Unexpected temporary directory');
    if(process.platform==='win32'){
      const command="$taskPath=(Resolve-Path -LiteralPath $env:SEEED_PERF_DIR).Path; if((Split-Path -Parent $taskPath) -ne $env:TEMP -or (Split-Path -Leaf $taskPath) -notlike 'seeed-performance-*'){throw 'Unexpected temporary directory'}; Remove-Item -LiteralPath $taskPath -Recurse -Force -ErrorAction Stop";
      const cleanup=spawnSync('powershell.exe',['-NoProfile','-Command',command],{windowsHide:true,env:{...process.env,SEEED_PERF_DIR:resolved},encoding:'utf8'});
      if(cleanup.status)throw Error('Temporary profile cleanup failed: '+cleanup.stderr);
    }else fs.rmSync(resolved,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
