/* Offline checks for model disambiguation, PDF page offsets and SKU matching. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
global.window={};
require(process.env.SEEED_TEST_CATALOG||path.join(root,'data/catalog.js'));
const db=window.SEEED_CATALOG;
const search=require(path.join(root,'search.js'))(db);
assert.equal(new Set(db.products.map(p=>p.sku)).size,db.stats.total);
for (const p of db.products) {
  if (p.image) assert(fs.existsSync(path.join(root,p.image)),p.sku);
  if (p.url) assert.equal(new URL(p.url).hostname,'www.seeedstudio.com');
}
for (const [query,sku] of [
  ['110110184','110110184'],
  ['客户点名 114110314，需要 Wi-Fi','114110314'],
  ['J4012 需要 Super 模式','110110145'],
  ['J4012，不需要 Super 模式，电源自备','110110184'],
  ['XIAO ESP32S3 Sense，需要摄像头','113991115'],
  ['R1100，客户需要 EU868','113991334'],
  ['R1014-10，客户需要 EU868','100025879'],
]) assert.equal(search.lookup(query).primary.sku,sku,query);
const q='J4012 需要 Super 模式';
const res=search.lookup(q);
assert.equal(search.alternatives(res.primary,q,res.needs)[0].p.sku,'114110314');
assert(!search.lookup('J4012 不需要 Super 模式').needs.some(t=>t.key==='super'));
assert(search.lookup('R1100').selection.includes('代表配置'));
const parts=search.bySku.get('113991334').accessories;
const eu=parts.filter(a=>a.name.includes('EU868'));
assert.deepEqual(eu.map(a=>a.sku),['114993268','114992628']);
assert(eu.every(a=>a.page===50&&a.printed===45));
for(const a of eu)assert(search.bySku.get(a.sku).url.includes('WM1302'));
assert(search.bySku.get('110110145').accessories.some(a=>a.sku==='112990246'));
assert(search.bySku.get('110110145').accessories.some(a=>a.sku==='E24121001'));
assert(search.bySku.get('114993556').series==='wifi');
assert(Object.values(db.docs).every(d=>!d.local && new URL(d.url).hostname==='files.seeedstudio.com'));
const verified=search.bySku.get('114110314').wikiEvidence[0];
assert.equal(new URL(verified.url).hostname,'wiki.seeedstudio.com');
assert(verified.en.includes('157 TOPS')&&verified.zh.includes('157 TOPS'));
assert(!search.bySku.get('110110191').wikiEvidence.some(item=>item.url===verified.url));
const english=require(path.join(root,'search.js'))(db,'en');
const englishRequest=english.lookup('J4012, need Super mode');
assert.equal(englishRequest.primary.sku,'110110145');
assert.equal(english.alternatives(englishRequest.primary,'J4012, need Super mode',englishRequest.needs)[0].p.sku,'114110314');
assert(!/[\u4e00-\u9fff]/.test(englishRequest.selection));
const r1014=search.bySku.get('100025879');
const attributes=Object.fromEntries(r1014.attributes.map(a=>[a.name,a.value]));
assert.deepEqual(Object.keys(attributes),['Product Type','Categories','Sensors','Series','RAM','Storage','Operating System','Network']);
assert.equal(attributes.RAM,'2GB');
assert.equal(attributes.Storage,'16GB');
assert.match(attributes.Network,/Wi-Fi/i);
assert(!r1014.parts.some(([name])=>name in attributes));
assert.equal(r1014.partEvidenceScope,'family');
assert.equal(r1014.storePartStatus,'empty');
assert.equal(r1014.parts.find(([name])=>/120.*resistor/i.test(name))[1],'5');
assert.match(r1014.partSources['DIN-rail clip'],/wiki\.seeedstudio\.com\/.+#din-rail-mounting-guide$/);
assert.equal(new Set(r1014.accessories.map(a=>a.sku)).size,25);
assert(search.bySku.get('110110145').parts.some(([item,qty])=>/Power Adapter/i.test(item)&&/1/.test(qty)));
for(const a of search.alternatives(r1014,'R1014-10 EU868',[]))assert.match(a.p.name,/^reComputer R10/);
if(db.audit) {
  const audit=db.audit, state=audit.detail;
  assert.equal(state.all,state.nonempty+state.empty+state.source_error+state.excluded+state.unread);
  assert.equal(state.checked,state.nonempty+state.empty);
  for(const [key,counts] of Object.entries(audit.fields)) {
    assert.equal(Object.values(counts).reduce((a,b)=>a+b,0),state.all,key);
  }
  const paired=['110990471','110060306'].map(sku=>search.bySku.get(sku));
  assert.equal(paired[0].url,paired[1].url);
  assert.notEqual(paired[0].storeId,paired[1].storeId);
  assert.equal(search.bySku.get('102110773').storePageStatus,'not_found');
  assert.equal(search.bySku.get('102110773').modelSpecs.find(x=>x.name==='RAM').value,'8GB');
  assert(search.bySku.get('102110773').modelSpecs.every(x=>x.source.endsWith('#page=17')));
  assert(search.bySku.get('206001697').specTables.some(t=>t.rows.length>=15));
  assert(audit.images.verifiedSkus+audit.images.missingSourceSkus+audit.images.failedSkus===db.stats.total);
  assert.equal(audit.documents.uniqueLinked,Object.values(audit.documents.uniqueByStatus).reduce((a,b)=>a+b,0));
  for(const p of db.products){
    const parts=new Set((p.parts||[]).map(([name])=>name));
    for(const [name,sku] of Object.entries(p.partProductSkus||{})){
      assert(parts.has(name),p.sku+' contains an unlisted linked component');
      assert(search.bySku.has(String(sku).toLowerCase()),p.sku+' has a missing linked component '+sku);
    }
    for(const [name,loc] of Object.entries(p.partSourceLocations||{})){
      assert(parts.has(name)&&loc.sheet&&loc.row>0,p.sku+' has an untraceable spreadsheet row');
    }
    const docs=p.documentAudit;
    if(docs)assert.equal(docs.linked,docs.checked+docs.unread+docs.failed,p.sku+' document accounting');
  }
}
console.log('Offline catalogue checks passed.',db.stats);
