/* Check the entry a colleague opens by double-clicking an extracted index.html. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');

async function checkPreview(browser, entry, width) {
  const page = await browser.newPage({viewport:{width, height:900}});
  const errors = [];
  const requests = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => {if (new URL(r.url()).pathname.startsWith('/api/')) requests.push(r.url());});
  try {
    await page.goto(entry + '#product=100025879&tab=attributes');
    const guide = page.locator('.preview-guide');
    const action = guide.locator('.workbench-link');
    await guide.waitFor();
    assert.match(await guide.innerText(), /只读目录预览/);
    assert.match(await guide.innerText(), /启动助手\.cmd/);
    assert.equal(await action.getAttribute('href'), 'http://127.0.0.1:8765/#product=100025879&tab=attributes');
    await page.locator('.tabs [data-tab="parts"]').click();
    assert.equal(await action.getAttribute('href'), 'http://127.0.0.1:8765/#product=100025879&tab=parts');
    await guide.getByRole('link', {name:'English'}).click();
    await page.getByRole('heading',{name:'You’re viewing the read-only catalogue'}).waitFor();
    assert.match(await guide.innerText(), /Start Assistant\.cmd/);
    assert.match(await page.locator('.hero-product').innerText(), /100025879/);
    assert.equal(await page.locator('.tabs [aria-selected=true]').getAttribute('data-tab'), 'parts');
    await page.goto(entry + '?lang=en#favorites');
    await page.getByRole('heading',{name:'Favorites',exact:true}).waitFor();
    assert.equal(await action.getAttribute('href'), 'http://127.0.0.1:8765/#favorites');
    assert.equal(await page.locator('[data-chat-action="toggle"], [data-wb-action="star"]').count(), 0);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    assert.deepEqual(requests, []);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
}

async function main() {
  const edge = path.join(process.env['ProgramFiles(x86)'] || '', 'Microsoft/Edge/Application/msedge.exe');
  const browser = await chromium.launch({headless:true, executablePath:fs.existsSync(edge) ? edge : undefined});
  try {
    const localFile = pathToFileURL(path.resolve(__dirname, '..', 'index.html')).href;
    const entries = [localFile, process.env.SEEED_TEST_PREVIEW_URL].filter(Boolean);
    for (const entry of entries) for (const width of [1440, 390]) await checkPreview(browser, entry, width);
    console.log('Read-only launch instructions, product tabs, language, Favorites link and mobile layout passed.');
  } finally { await browser.close(); }
}

main().catch(e => { console.error(e); process.exitCode=1; });
