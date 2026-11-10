/* Exercise native and on-screen history with a synthetic local profile and no network access. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

const root=path.resolve(__dirname,'..');
const origin='http://127.0.0.1:58743/';
const primary='100025879', other='100011197';
const before='[data-history="-1"]', after='[data-history="1"]';
const preference='seeed-workbench.favorites-sidebar.expanded';
const assets=new Set(['index.html','app.css','app.js','search.js','product-ui.js','workbench.js','workbench.css','chat.js','chat.css','data/catalog.js']);
const data=fs.readFileSync(path.join(root,'data/catalog.js'));

async function localBrowser(browser,language='zh-CN',width=1320){
  const page=await browser.newPage({viewport:{width,height:900}});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const profile={csrf:'test-fixture',language,favorites:[primary,other],projects:[{id:'project-a',title:'Example project',description:'Saved',labels:['Lab'],skus:[primary]}],
    provider:'deepseek',providers:{deepseek:{hasKey:false,model:'demo'}},customizableSkus:[primary,other],customEvidence:{},
    overrides:{[primary]:{sku:primary,customConfirmed:true},[other]:{sku:other,customConfirmed:true}}};
  await page.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!==new URL(origin).origin)return route.abort();
    if(request.method()!=='GET'){errors.push('Unexpected write '+url.pathname);return route.abort();}
    if(url.pathname==='/api/state')return route.fulfill({json:profile});
    if(url.pathname.startsWith('/api/')){errors.push('Unexpected API read '+url.pathname);return route.abort();}
    const file=url.pathname.slice(1)||'index.html';
    if(!assets.has(file))return route.fulfill({status:204});
    if(file==='data/catalog.js')return route.fulfill({contentType:'application/javascript',body:data});
    return route.fulfill({path:path.join(root,file)});
  });
  return {page,errors};
}
const current=(page,id)=>page.locator('.tabs [aria-selected="true"][data-tab="'+id+'"]').waitFor();
const go=(page,view)=>page.locator('[data-view="'+view+'"]').first().click();
const product=(page,sku)=>page.locator('.hero-product').filter({hasText:sku}).waitFor();

async function catalogueAndProjects(browser){
  const {page,errors}=await localBrowser(browser);
  try{
    await page.goto(origin+'#product='+primary+'&tab=notes');
    await current(page,'accessories');
    const favorites=page.locator('#wb-fav-toggle');
    assert.equal(await favorites.getAttribute('aria-expanded'),'false');
    assert.equal(await page.evaluate(key=>localStorage.getItem(key),preference),null);
    await favorites.press('Enter');
    await page.reload();await current(page,'accessories');
    assert.equal(await favorites.getAttribute('aria-expanded'),'true');
    await favorites.click();await page.reload();await current(page,'accessories');
    assert.equal(await favorites.getAttribute('aria-expanded'),'false');

    await page.goto(origin+'#product=113991334&tab=accessories');await current(page,'accessories');
    const offers=page.locator('[data-nav-disclosure="offers"]');
    assert.equal(await offers.evaluate(el=>el.open),false);
    await offers.locator('summary').click();assert(await offers.evaluate(el=>el.open));
    await page.locator('.tabs [data-tab="docs"]').click();await page.goBack();await current(page,'accessories');
    assert(await offers.evaluate(el=>el.open));
    for(const text of ['wifi','Wi-Fi','WIFI','wi-fi','Wi‑Fi'])await page.locator('#accfilter').fill(text);
    await page.reload();await current(page,'accessories');
    assert.equal(await page.locator('#accfilter').inputValue(),'Wi‑Fi');
    await page.locator('#accfilter').fill('wifi before native Back');
    await page.goBack();await page.goForward();await product(page,'113991334');
    assert.equal(await page.locator('#accfilter').inputValue(),'wifi before native Back');
    await page.locator('#asktext').fill('R1100 EU868');
    await page.locator('#ask button').click();await current(page,'accessories');
    await page.locator('#accfilter').fill('SPI');
    await page.locator('#tabbody a[href="#product=114993268"]').first().click();
    await product(page,'114993268');await page.locator(before).click();
    await current(page,'accessories');
    assert.equal(await page.locator('#asktext').inputValue(),'R1100 EU868');
    assert.equal(await page.locator('#accfilter').inputValue(),'SPI');
    await page.goForward();await product(page,'114993268');

    await go(page,'catalog');
    await page.locator('#category').selectOption('menu');
    await page.locator('#cattext').fill('Grove');
    await page.locator('[data-page="1"]').click();
    const row=page.locator('.directory table .sku').first();
    const sku=await row.innerText();
    await row.click();await product(page,sku);await page.goBack();
    await page.locator('#cattext').waitFor();
    assert.equal(await page.locator('#category').inputValue(),'menu');
    assert.equal(await page.locator('#cattext').inputValue(),'Grove');
    assert.match(await page.locator('.pager').innerText(),/2\s*\//);
    assert.equal(await row.innerText(),sku);
    await page.reload();await page.locator('#cattext').waitFor();
    assert.equal(await page.locator('#cattext').inputValue(),'Grove');
    await page.locator(after).click();await product(page,sku);

    await go(page,'favorites');await page.locator('[data-wb-fav-check="'+primary+'"]').check();
    await page.locator('#wb-target-project').selectOption('project-a');
    await page.locator('[data-wb-action="favorites-project"]').click();
    await page.locator('#wb-project-title').waitFor();
    await page.locator('#wb-project-description').fill('Unsaved demo for navigation.');
    await page.locator('#wb-workbench [data-wb-action="open"][data-wb-sku="'+primary+'"]').first().click();
    await product(page,primary);await page.locator(before).press('Enter');
    await page.locator('#wb-project-description').waitFor();
    assert.equal(await page.locator('#wb-project-description').inputValue(),'Unsaved demo for navigation.');
    assert(!JSON.stringify(await page.evaluate(()=>[history.state,{...sessionStorage}])).includes('Unsaved demo'));
    await page.locator(before).click();await page.locator('#wb-target-project').waitFor();
    assert(await page.locator('[data-wb-fav-check="'+primary+'"]').isChecked());
    assert.equal(await page.locator('#wb-target-project').inputValue(),'project-a');
    await go(page,'developer');
    await page.locator('#wb-key').fill('fixture-private-value');
    await page.locator('[data-wb-action="devtab"][data-wb-id="products"]').click();
    await page.locator('#wb-edit-query').waitFor();
    await page.goBack();await page.locator('#wb-key').waitFor();
    assert.equal(await page.locator('#wb-key').inputValue(),'');
    assert(!JSON.stringify(await page.evaluate(()=>[history.state,{...sessionStorage}])).includes('fixture-private'));
    assert.deepEqual(errors,[]);
  }catch(e){console.error('Page:',page.url(),(await page.locator('body').innerText()).slice(0,700),errors);throw e;}finally{await page.close();}
}

async function fivePages(browser){
  const {page,errors}=await localBrowser(browser,'en',390);
  try{
    await page.goto(origin+'#product='+primary+'&tab=attributes');
    await current(page,'specs');
    assert(await page.locator(before).isDisabled());assert(await page.locator(after).isDisabled());
    const steps=['parts','docs','specs','accessories','docs','parts','specs'];
    for(const tab of steps)await page.locator('.tabs [data-tab="'+tab+'"]').click();
    for(let i=1;i<=5;i++){await page.locator(before).click();await current(page,steps[steps.length-i-1]);}
    assert(await page.locator(before).isDisabled());
    await page.reload();await current(page,'docs');
    assert(await page.locator(before).isDisabled());
    assert.equal(await page.locator(after).getAttribute('aria-label'),'Forward');
    for(let i=2;i<steps.length;i++){await page.locator(after).click();await current(page,steps[i]);}
    assert(await page.locator(after).isDisabled());
    await page.goBack();await current(page,'parts');
    await page.locator('.tabs [data-tab="docs"]').click();assert(await page.locator(after).isDisabled());
    assert.equal(await page.locator('#wb-fav-toggle').getAttribute('aria-expanded'),'false');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
}

async function filePreview(browser){
  const page=await browser.newPage();
  try{
    await page.goto(pathToFileURL(path.join(root,'index.html')).href+'#product='+primary+'&tab=parts');
    await current(page,'parts');await go(page,'catalog');await page.goBack();await current(page,'parts');
    await page.locator(after).click();await page.locator('#category').waitFor();
  }finally{await page.close();}
}

(async()=>{
  const edge=path.join(process.env['ProgramFiles(x86)']||'','Microsoft/Edge/Application/msedge.exe');
  const browser=await chromium.launch({headless:true,executablePath:fs.existsSync(edge)?edge:undefined});
  try{await catalogueAndProjects(browser);await fivePages(browser);await filePreview(browser);}
  finally{await browser.close();}
  console.log('Passed desktop, narrow English and file preview navigation, five-step branching and local favorite preferences.');
})().catch(error=>{console.error(error);process.exitCode=1;});
