/* Invoked only by tools.verify_chat against a disposable loopback profile. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');

async function run(){
  const origin=new URL(process.env.SEEED_CHAT_FIXTURE);
  assert(origin.hostname==='127.0.0.1'&&origin.port!=='8765');
  const edge=path.join(process.env['ProgramFiles(x86)']||'','Microsoft/Edge/Application/msedge.exe');
  const browser=await chromium.launch({headless:true,executablePath:fs.existsSync(edge)?edge:undefined});
  try{
    const page=await browser.newPage({viewport:{width:1480,height:1000}});
    const issues=[];
    page.on('pageerror',e=>issues.push(e.message));
    const action=n=>page.locator('[data-chat-action="'+n+'"]');
    const context=page.locator('[data-chat-node=context]');
    const input=page.locator('[data-chat-node=input]');
    async function send(text,count){
      await input.fill(text);
      await input.press('Enter');
      await page.locator('.sc-answer').filter({hasText:'Fixture reply '+count}).waitFor();
    }
    await page.goto(origin.href+'#product=114110314&tab=notes');
    await page.locator('.hero-product').waitFor();
    const favorite=page.locator('#wb-fav-toggle');
    await favorite.focus();await favorite.press('Space');
    assert.equal(await favorite.getAttribute('aria-expanded'),'false');
    await page.reload();await favorite.waitFor();
    assert.equal(await favorite.getAttribute('aria-expanded'),'false');
    assert.equal(await page.locator('#wb-fav-list').isVisible(),false);
    await favorite.press('Enter');
    assert.match(await page.locator('#wb-fav-list').innerText(),/J4012/);
    assert.equal(await page.locator('#ai-panel,#open-ai-rail').count(),0);
    await action('toggle').click();
    assert.match(await context.innerText(),/114110314/);
    await send('What is documented as manual?',1);
    await page.goto(origin.href+'#product=100025879&tab=accessories');
    await page.locator('#accfilter').fill('EU868');
    assert.match(await context.innerText(),/100025879/);
    await send('Compare with the previous device.',2);
    await action('new').click();
    await page.goto(origin.href+'#catalog');
    await page.locator('#cattext').fill('XIAO');
    assert.match(await context.innerText(),/XIAO/);
    await send('What collection is on this page?',3);
    await page.goto(origin.href+'#custom');
    await page.locator('[data-wb-action=new-from-sku][data-wb-sku="114110314"]').click();
    await page.locator('#wb-project-title').fill('Fixture work order');
    await page.locator('#wb-project-labels').fill('mount');
    await page.locator('#wb-project-description').fill('Fixture draft only: wall mounting');
    await send('Summarize this project requirement.',4);
    await page.goto(origin.href+'#developer');
    await page.locator('#wb-key').fill('unsaved-secret-fixture');
    await send('What can I do in this tab?',5);
    await action('close').click();
    await page.reload();await action('toggle').click();
    await page.locator('.sc-answer').filter({hasText:'Fixture reply 5'}).waitFor();
    await page.locator('.sc-thread[data-chat-id]').filter({hasText:'What is documented'}).click();
    await page.locator('.sc-answer').filter({hasText:'Fixture reply 2'}).waitFor();
    assert.equal(await page.locator('.sc-answer').count(),2);
    await page.setViewportSize({width:390,height:844});
    assert(await page.locator('#seeed-chat-panel').isVisible());
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await input.press('Escape');
    assert.equal(await action('toggle').getAttribute('aria-expanded'),'false');
    assert.deepEqual(issues,[]);
  }finally{await browser.close();}
}
run().catch(e=>{console.error(e);process.exitCode=1;});
