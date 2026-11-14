/* Offline checks for model disambiguation, PDF page offsets and SKU matching. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
global.window={};
require(process.env.SEEED_TEST_CATALOG||path.join(root,'data/catalog.js'));
const db=window.SEEED_CATALOG;
const search=require(path.join(root,'search.js'))(db);
const fixtureAccessory={name:'Fixture accessory',source:'https://wiki.seeedstudio.com/fixture/',bazaarCheck:{
  status:'confirmed',checkedAt:'2026-01-01',match:{sku:'FIXTURE-STORE',name:'Verified fixture accessory',url:'https://www.seeedstudio.com/fixture.html'}}};
assert.equal(search.accessoryMatch(fixtureAccessory).product.sku,'FIXTURE-STORE');
assert.equal(search.accessoryMatch(fixtureAccessory).product.isExternal,true);
assert.equal(search.accessoryMatch({...fixtureAccessory,bazaarCheck:{...fixtureAccessory.bazaarCheck,status:'candidates'}}),null);
assert.equal(search.accessoryMatch({...fixtureAccessory,publishedSku:'DIFFERENT-SKU'}),null);
assert.equal(search.accessoryMatch({...fixtureAccessory,sku:'FIXTURE-STORE',productUrl:'https://www.seeedstudio.com/fixture.html'}).product.isExternal,true);
assert.equal(search.accessoryMatch({...fixtureAccessory,sku:'FIXTURE-STORE',productUrl:'https://www.seeedstudio.com/another-model.html'}),null);
const vm=require('node:vm');
const productUI={};vm.createContext(productUI);vm.runInContext(fs.readFileSync(path.join(root,'product-ui.js'),'utf8'),productUI);
const officialExample=db.products.find(p=>p.sku==='110110145');
const internal={'110110145':{sku:'110110145',name:officialExample.name,eol:true},'TEST-INTERNAL':{sku:'TEST-INTERNAL',name:'Internal example sensor',internalOnly:true}};
const privateView=productUI.mergeProductData(db,{},internal),privateSearch=require(path.join(root,'search.js'))(privateView);
assert.equal(privateSearch.lookup('110110145').primary.internal.eol,true);
assert(!privateSearch.lookup('wifi').ranked.some(row=>row.p.internal?.eol));
assert(!privateSearch.alternatives(privateSearch.bySku.get('110110184'),'J4012',[]).some(row=>row.p.internal?.eol));
assert.equal(privateSearch.lookup('TEST-INTERNAL').primary.sku,'TEST-INTERNAL');
assert.equal(privateSearch.lookup('Internal example sensor').primary.sku,'TEST-INTERNAL');
assert.equal(privateSearch.bySku.get('test-internal').url,'');
assert.equal(officialExample.internal,undefined);
assert.equal(privateView.products.length,db.products.length+1);
const {normalizeCatalogText,catalogTextMatches}=require(path.join(root,'search.js'));
const choices=q=>search.lookup(q).ranked.slice(0,12).map(hit=>hit.p.sku);
const wifi=['wifi','WI-FI','Wi‑Fi','ＷＩＦＩ','wi fi','WLAN'];
const power=['power adapter','Power Adaptor','POWER-ADAPTER','电源适配器','電源適配器'];
for(const terms of [wifi,power])for(const query of terms){
  assert.equal(normalizeCatalogText(query),normalizeCatalogText(terms[0]));
  assert.deepEqual(choices(query),choices(terms[0]),query);
}
assert.match(search.lookup('电源适配器').primary.name,/Power Adapter/i);
assert(!/without|w\/o/i.test(search.lookup('power adapter').primary.name.split('Power Adapter')[0]));
assert(catalogTextMatches('wifi 天线','Raspberry Pi CM4','Wi-Fi/BLE Antenna'));
assert(catalogTextMatches('电源适配器','American-standard POWER ADAPTOR'));
assert(!catalogTextMatches('power adapter','power cable','wireless adapter'));
assert(!catalogTextMatches('114993268','1149932680'));
assert(!catalogTextMatches('E24121001','E241210012'));
assert(search.matchesText(['Power Adaptor','EU plug'],'电源适配器'));
assert(!search.lookup('J4012 不需要 WI-FI').needs.some(t=>t.key==='wifi'));
assert.equal(search.lookup('110110191 power adapter').primary.sku,'110110191');
const industrial=search.bySku.get('110110191');
const oldRadio=industrial.accessories.find(a=>a.name.includes('EC25EUXGA'));
const successor=search.accessoryMatch(oldRadio);
assert.equal(successor.method,'successor');
assert.equal(successor.product.sku,'113991135');
assert.match(successor.source,/#page=1$/);
assert.match(successor.skuSource,/#page=3$/);
assert.match(successor.product.url,/EC25-EUX-mini-PCIe-p-5669/);
assert.equal(search.lookup('EC25EUXGA-MINIPCIE').primary.sku,'113991135');
for(const name of ['EC25EUGA-MINIPCIE 4G module','EC25EUXGA-MINIPCIE antenna kit','EC20CEHCLG-MINIPCIE 4G module','WM1303 LoRaWAN gateway module (SPI, EU868)','RTL8822CE','Power adapter (optional)']){
  assert.equal(search.accessoryMatch({...oldRadio,name}),null,name);
}
assert.equal(search.accessoryMatch({...oldRadio,sku:'not-a-real-sku'}),null);
assert.equal(search.accessoryMatch({...oldRadio,sku:'113991135',publishedSku:'113991134'}),null);
assert.equal(search.accessoryMatch({...oldRadio,sku:'113991135',productUrl:search.bySku.get('113991134').url}),null);
assert.equal(search.accessoryMatch({...oldRadio,source:'https://example.org/uncited-part'}),null);
assert.equal(search.accessoryMatch({productUrl:search.bySku.get('110990471').url}),null,'Two SKUs share a store URL');
const realPart='2.4GHz FPC Antenna A-02 for XIAO ESP32-S3';
const kit=search.bySku.get('100069905');
assert(kit.parts.some(([name])=>name===realPart));
assert.equal(search.accessoryMatch({name:realPart,source:kit.partSources?.[realPart]||kit.partSource||kit.url}).product.sku,'318020968');
const panel= db.products.flatMap(p=>p.accessories||[]).find(a=>a.name==='2.7-inch e-paper display panel');
assert.equal(search.accessoryMatch(panel).product.sku,'104990054');
assert.equal(search.accessoryMatch({...panel,name:'2.7-inch e-paper display HAT'}),null);
const original=search.bySku.get('318020968');
const small={products:[kit,original]};
const altered={products:[kit,{...original,name:'Invented model 123 X'}]};
const localSearch=require(path.join(root,'search.js'))(altered,'en',()=>false,small);
assert.equal(localSearch.accessoryMatch({name:'Invented model 123 X',source:kit.url}),null);
assert.equal(localSearch.accessoryMatch({name:realPart,source:kit.url}).product.name,original.name);
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
