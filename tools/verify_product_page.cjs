/* Read-only browser checks. The optional language override is local to each browser tab. */
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');

async function check(){
  const possibleEdge=path.join(process.env['ProgramFiles(x86)']||'', 'Microsoft/Edge/Application/msedge.exe');
  const browser=await chromium.launch({headless:true,executablePath:fs.existsSync(possibleEdge)?possibleEdge:undefined});
  try {
    for(const language of ['zh-CN','en']){
      const page=await browser.newPage({viewport:{width:1440,height:1000}});
      const issues=[];
      page.on('pageerror',e=>issues.push(e.message));
      await page.route('**/api/state',async route=>{
        const original=await route.fetch();
        const profile=await original.json();
        await route.fulfill({response:original,json:{...profile,language}});
      });
      await page.route('**/api/ai',route=>{issues.push('Unrequested AI call');return route.abort();});
      const origin=process.env.SEEED_TEST_URL||'http://127.0.0.1:8765/';
      await page.goto(origin+'#product=100025879');
      await page.locator('.hero-product').waitFor();
      assert.equal(await page.locator('.tabs [aria-selected=true]').getAttribute('data-tab'),'specs');
      assert.equal(await page.locator('#tabbody .model-details tbody tr').count(),8);
      assert.equal(await page.locator('.tabs [data-tab=attributes], .tabs [data-tab=notes]').count(),0);
      assert.match(await page.locator('.spec-highlights').innerText(),/2GB/);
      assert.match(await page.locator('.spec-highlights').innerText(),/16GB/);
      assert.match(await page.locator('.detail-key').innerText(),/25/);
      assert.match(await page.locator('.detail-key').innerText(),/Logo/i);
      await page.locator('.tabs [data-tab=parts]').click();
      assert.equal(await page.locator('#tabbody tbody tr').count(),3);
      const resistor=page.locator('#tabbody tr').filter({hasText:/termination resistor/i});
      assert.equal(await resistor.locator('td').nth(1).innerText(),'5');
      assert.match(await resistor.locator('a').getAttribute('href'),/#page=18$/);
      const clip=page.locator('#tabbody tr').filter({hasText:/DIN-rail clip/i});
      assert.equal(await clip.locator('td').nth(1).innerText(),'');
      assert.match(await clip.locator('a').getAttribute('href'),/#din-rail-mounting-guide$/);
      assert.match(page.url(),/tab=parts$/);
      await page.reload();
      await page.locator('.tabs [data-tab=parts][aria-selected=true]').waitFor();
      await page.locator('.tabs [data-tab=accessories]').click();
      await page.locator('#accfilter').fill('EU868');
      assert.equal(await page.locator('#tabbody tbody tr').count(),2);
      assert.match(await page.locator('#tabbody').innerText(),/114993268/);
      assert.match(await page.locator('#tabbody').innerText(),/114992628/);
      await page.goto(origin+'#product=100011197&tab=attributes');
      await page.locator('.hero-product').filter({hasText:'100011197'}).waitFor();
      assert.match(await page.locator('#tabbody').innerText(),/64GB eMMC/);
      assert.match(await page.locator('#tabbody').innerText(),/8GB/);
      await page.goto(origin+'#product=113991334&tab=parts');
      await page.locator('.hero-product').filter({hasText:'113991334'}).waitFor();
      assert((await page.locator('#tabbody tbody tr').count())>=7);
      await page.goto(origin+'#product=100025879&tab=attributes');
      await page.locator('.tabs [data-tab=specs][aria-selected=true]').waitFor();
      await page.setViewportSize({width:390,height:844});
      const width=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:window.innerWidth}));
      assert(width.document<=width.viewport+1,JSON.stringify(width));
      assert.deepEqual(issues,[]);
      await page.close();
    }
    console.log('Desktop + mobile product records passed in Chinese and English.');
  } finally {await browser.close();}
}

check().catch(error=>{console.error(error);process.exitCode=1;});
