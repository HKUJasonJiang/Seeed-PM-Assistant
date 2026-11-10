/* Exercise the same published catalogue through file:// and an isolated full workbench. */
const assert=require('node:assert/strict');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

async function check(browser,entry,language,width){
  const page=await browser.newPage({viewport:{width,height:900}});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  // The supplied service is an isolated test instance. Override language per tab.
  if(entry.startsWith('http'))await page.route('**/api/state',async route=>{
    const response=await route.fetch(),state=await response.json();
    await route.fulfill({response,json:{...state,language}});
  });
  const open=async (sku,tab)=>{
    await page.goto(entry+'?lang='+language+'#product='+sku+'&tab='+tab);
    await page.locator('.hero-product').filter({hasText:sku}).waitFor();
  };
  try{
    await open('110110191','notes');
    assert.match(await page.title(),language==='en'?/L1 Light Customization Assistant/:/L1轻定制小助手/);
    await page.locator('.tabs [data-tab=accessories][aria-selected=true]').waitFor();
    const filter=page.locator('#accfilter');
    await filter.fill('EC25EUXGA');
    const row=page.locator('#tabbody tbody tr').filter({hasText:'EC25EUXGA-MINIPCIE'});
    assert.equal(await row.count(),1);
    assert.match(await row.innerText(),/GA → GR/);
    assert.equal(await row.locator('a[href="#product=113991135"]').count(),1);
    const sources=await row.locator('a').evaluateAll(links=>links.map(a=>a.href));
    assert.equal(new Set(sources).size,sources.length,'Each distinct source should appear once per item');
    assert(sources.some(url=>url.includes('Industrial-Reference-Guide.pdf#page=18')));
    assert(sources.some(url=>url.includes('ec21euxga-128-sgns.pdf#page=1')));
    assert(sources.some(url=>url.includes('reComputer-R1100-flyer.pdf#page=3')));
    assert(sources.some(url=>url.startsWith('https://www.seeedstudio.com/')));
    assert(!sources.some(url=>url.includes('113991134')));
    await filter.fill('EC20CEHCLG');
    assert.equal(await page.locator('#tabbody tbody tr a.sku').count(),0);
    let previous;
    for(const term of ['wifi','WIFI','wi-fi','Wi-Fi']){
      await filter.fill(term);
      const text=await page.locator('#tabbody tbody tr').allTextContents();
      assert(text.some(s=>s.includes('8723')));
      if(previous)assert.deepEqual(text,previous);
      previous=text;
    }
    await open('110110145','accessories');
    const offers=page.locator('details[data-offer-sku]');
    assert.equal(await offers.getAttribute('open'),null);
    await offers.locator('summary').click();
    assert(await offers.evaluate(e=>e.open));
    await page.reload();await offers.waitFor();
    assert(await offers.evaluate(e=>e.open));
    await offers.locator('summary').click();
    await filter.fill('电源适配器');
    const zh=await page.locator('#tabbody tbody tr').allTextContents();
    await filter.fill('power adapter');
    assert(zh.length>0);
    assert.deepEqual(zh,await page.locator('#tabbody tbody tr').allTextContents());
    await open('100025879','attributes');
    assert.equal(await page.locator('.tabs [aria-selected=true]').getAttribute('data-tab'),'specs');
    assert.equal(await page.locator('.model-details tbody tr').count(),8);
    assert.match(await page.locator('.model-details').innerText(),/16GB/);
    assert.equal(await page.locator('.tabs [data-tab=attributes], .tabs [data-tab=notes]').count(),0);
    await page.locator('[data-view="catalog"]').first().click();
    const catalog=page.locator('#cattext');
    await catalog.fill('电源适配器');const count=await page.locator('.catalog-count').innerText();
    await catalog.fill('power adapter');
    assert.equal(await page.locator('.catalog-count').innerText(),count);
    assert(Number(count.replace(/[^0-9]/g,''))>0);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
}
(async()=>{
  const edge=path.join(process.env['ProgramFiles(x86)'],'Microsoft/Edge/Application/msedge.exe');
  const browser=await chromium.launch({executablePath:edge,headless:true});
  try{
    const entries=[pathToFileURL(path.resolve(__dirname,'..','index.html')).href];
    if(process.env.SEEED_TEST_URL)entries.push(process.env.SEEED_TEST_URL);
    for(const entry of entries)for(const [lang,width] of [['zh-CN',1440],['en',390]])await check(browser,entry,lang,width);
    console.log('Merged options, original/successor evidence, regional isolation, folded offers, old URLs and bilingual search passed.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
