/* Read-only check of a running installation. No settings, histories or model calls are written. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {chromium}=require('playwright');

async function verify(){
  const origin=process.env.SEEED_TEST_URL||'http://127.0.0.1:8765/';
  const edge=path.join(process.env['ProgramFiles(x86)']||'','Microsoft/Edge/Application/msedge.exe');
  const browser=await chromium.launch({headless:true,executablePath:fs.existsSync(edge)?edge:undefined});
  try{
    for(const [language,width] of [['zh-CN',1440],['en',1440],['zh-CN',390],['en',390]]){
      const page=await browser.newPage({viewport:{width,height:width>600?1000:844}});
      const issues=[];
      page.on('pageerror',e=>issues.push(e.message));
      await page.route('**/api/**',async route=>{
        if(route.request().method()!=='GET'){issues.push('Unexpected write');return route.abort();}
        if(new URL(route.request().url()).pathname==='/api/state'){
          const original=await route.fetch(),view=await original.json();
          for(const provider of Object.values(view.providers||{}))provider.hasKey=false;
          return route.fulfill({response:original,json:{...view,language}});
        }
        return route.continue();
      });
      const action=n=>page.locator('[data-chat-action="'+n+'"]');
      const ctx=page.locator('[data-chat-node=context]');
      const drawer=page.locator('#seeed-chat-panel');
      await page.goto(origin+'#product=100025879&tab=attributes');
      await action('toggle').waitFor();
      assert.equal(await action('toggle').count(),1);
      await action('toggle').focus();await action('toggle').press('Enter');
      await drawer.waitFor();
      assert.match(await ctx.innerText(),/100025879/);
      assert(await action('settings').isVisible());
      assert(await page.locator('.sc-send').isDisabled());
      if(process.env.SEEED_CHAT_SCREENSHOT && language==='zh-CN'&&width===1440){
        const screenshot=path.join(os.tmpdir(),'seeed-product-chat-20261108.png');
        await page.screenshot({path:screenshot});console.log(screenshot);
      }
      await action('settings').click();await page.locator('#wb-key').waitFor();
      await action('toggle').click();
      assert(!/100025879/.test(await ctx.innerText()));
      await action('close').click();
      await page.goto(origin+'#favorites');await action('toggle').click();
      assert(!/100025879/.test(await ctx.innerText()));
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await action('close').click();
      const fav=page.locator('#wb-fav-toggle');
      const previous=await fav.getAttribute('aria-expanded');
      await fav.focus();await fav.press('Space');await page.reload();await fav.waitFor();
      assert.notEqual(await fav.getAttribute('aria-expanded'),previous);
      assert.deepEqual(issues,[]);
      await page.close();
    }
    console.log('Open, settings, page switch and remembered favorites passed at 390 and 1440 pixels in zh/en.');
  }finally{await browser.close();}
}
verify().catch(e=>{console.error(e);process.exitCode=1;});
