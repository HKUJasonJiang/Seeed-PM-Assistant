(() => {
  'use strict';
  const view=document.getElementById('view');
  const publicPreview=Boolean(document.querySelector('meta[name="seeed-public-preview"]'));
  const loopback=['127.0.0.1','localhost','[::1]'].includes(location.hostname);
  let base=window.SEEED_CATALOG;
  const missingFiles=[];
  if(!Array.isArray(base?.products)||!base.products.length)missingFiles.push('data/catalog.js');
  if(typeof createSearch!=='function')missingFiles.push('search.js');
  if(typeof mergeProductData!=='function')missingFiles.push('product-ui.js');
  if(missingFiles.length){view.textContent='未能读取所需文件 / Could not load: '+missingFiles.join(', ');return;}
  let db=base, search, currentProduct, currentAlternatives=[];
  let profile={language:'zh-CN',provider:'deepseek',providers:{},favorites:[],projects:[],overrides:{}};
  let lang='zh-CN', connected=false;
  const state={view:'assistant',query:'J4012',pin:'',tab:'',accFilter:'',catalogQuery:'',group:'*',page:1};
  const views=new Set(['assistant','catalog','coverage','favorites','custom','developer']);
  const historyWindow=5;
  const boundsKey='seeed-workbench.page-history.'+location.pathname;
  const snapshotsKey=boundsKey+'.snapshots';
  let entry=null, bounds=null, writeTimer=null, restoring=false;
  const recentEntries=new Map();
  try{
    const saved=JSON.parse(sessionStorage.getItem(snapshotsKey)||'[]');
    for(const item of saved.slice(-(historyWindow*2+1)))if(item?.id&&views.has(item.snapshot?.page?.view))recentEntries.set(item.id,item);
  }catch{ /* Session storage can be disabled for file previews. */ }
  let catalogPage={skus:[],total:0};
  const t=(zh,en)=>lang==='en'?en:zh;
  const local=v=>localizedProductText(v,lang);
  const h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const productLabel=(p,value,badge=true)=>window.InternalUI?.label(search?.bySku.get(String(p?.sku||'').toLowerCase())||p,value,lang,badge)||h(value);
  const num=n=>Number(n||0).toLocaleString(lang==='en'?'en-US':'zh-CN');
  const safe=u=>typeof u==='string'&&(/^https?:\/\//i.test(u)||/^(?:data\/jpg\/|\/user-images\/)[a-z\d._-]+$/i.test(u));
  const link=(url,label,cls='')=>safe(url)?`<a class="${cls}" href="${h(url)}" target="_blank" rel="noopener noreferrer">${h(label)}</a>`:'';
  const short=p=>p.name.match(/^reComputer\s+(?:(?:Industrial|Super|Robotics|Rugged)\s+)?[JR]\d+(?:-\d+)?(?:\s*\(w\/o power adapter\))?/i)?.[0]||p.name;
  const photo=(p,cls='')=>`<div class="photo ${cls}">${safe(p.image||(!p.detailAudit&&p.imageUrl))?`<img loading="lazy" src="${h(p.image||p.imageUrl)}" alt="${h(p.name)}">`:''}</div>`;
  const productLink=(p,label=p.sku,cls='sku')=>`<a class="${cls}" href="#product=${encodeURIComponent(p.sku)}">${productLabel(p,label)}</a>`;
  const storeOffer=a=>a.type==='商品页 Also Add 加购项'&&!a.documentedAsAccessorySource;
  const title=(name,desc)=>`<div class="page-title"><h1>${h(name)}</h1><p>${h(desc)}</p></div>`;
  const table=(heads,rows)=>`<div class="table-scroll"><table><thead><tr>${heads.map(x=>`<th>${h(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${c||''}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const el=id=>document.getElementById(id);
  const price=p=>{
    const fmt=v=>new Intl.NumberFormat('en-US',{style:'currency',currency:p.currency||'USD'}).format(v);
    const note=p.storePageStatus==='not_found'?t('留档价 · ','Archived price · '):'';
    if(p.price>0)return note+(p.maxPrice>p.price?fmt(p.price)+' – '+fmt(p.maxPrice):fmt(p.price))+' '+(p.currency||'');
    return p.maxPrice>0?note+t('最高 '+fmt(p.maxPrice)+' · 起价待核','Up to '+fmt(p.maxPrice)+' · minimum unconfirmed'):'';
  };
  async function api(path,options={}){
    if(location.protocol==='file:')throw Object.assign(new Error(t('请用启动助手打开本地服务。','Open the local launcher first.')),{code:'service_offline'});
    const method=(options.method||'GET').toUpperCase();
    const settings={method,cache:'no-store',headers:{},signal:options.signal};
    if(method!=='GET'){
      settings.headers={'Content-Type':'application/json','X-CSRF-Token':profile.csrf||''};
      if(options.body!==undefined)settings.body=JSON.stringify(options.body);
    }
    const response=await fetch(path,settings);
    const result=await response.json();
    if(!response.ok){const err=new Error(result.message||result.error||response.statusText);err.code=result.code||result.error;err.status=response.status;throw err;}
    return result;
  }
  let indexedBase, indexedProfile='', indexedLanguage='';
  let directoryText=new Map();
  function rebuild(){
    const internalVersion=profile.internalSummary?.version;
    const signature=JSON.stringify([profile.overrides||{},internalVersion?[internalVersion,profile.internalSummary.matched,profile.internalSummary.unmatched]:profile.internalProducts||{}]);
    if(indexedBase!==base||indexedProfile!==signature){
      db=mergeProductData(base,profile.overrides,profile.internalProducts);
      indexedBase=base;indexedProfile=signature;directoryText=new Map();search=null;
    }
    if(!search||indexedLanguage!==lang){
      search=createSearch(db,lang,p=>connected?window.Workbench.isEligible(p):Boolean(p.custom||p.customConfirmed),base);
      indexedLanguage=lang;
    }
    optionCache=null;
  }
  async function reloadData(reloadBase=false){
    if(reloadBase){
      const resp=await fetch('data/catalog.js',{cache:'no-store'});
      if(!resp.ok)throw Error(t('目录加载失败。','Catalogue could not be loaded.'));
      const raw=(await resp.text()).trim().replace(/^window\.SEEED_CATALOG\s*=\s*/,'').replace(/;$/,'');
      const parsed=JSON.parse(raw);if(!Array.isArray(parsed.products))throw Error('Invalid catalogue');
      window.SEEED_CATALOG=base=parsed;
    }
    profile=await api('/api/state');
    lang=profile.language==='en'?'en':'zh-CN';connected=true;
    rebuild();render();return profile;
  }
  const snapLang=v=>{lang=v==='en'?'en':'zh-CN';profile.language=lang;rebuild();render();};
  function changeView(name){
    if(!views.has(name))return;
    state.view=name;render();recordNavigation('push');window.scrollTo(0,0);
  }
  function openProduct(sku){navigateHash('#product='+encodeURIComponent(sku));}
  const workspaceLink=()=> 'http://127.0.0.1:8765/'+location.hash;
  function previewGuide(){
    const locale=lang==='en'?'zh-CN':'en';
    const docs='https://github.com/HKUJasonJiang/Seeed-PM-Assistant/blob/main/'+(lang==='en'?'README.md':'README.zh-CN.md');
    return `<section class="preview-guide" aria-labelledby="preview-heading"><div class="preview-guide-body"><h2 id="preview-heading">${t('当前是只读目录预览','You’re viewing the read-only catalogue')}</h2>`+
      `<p>${t('在这里可以查产品。收藏、定制项目、AI 对话和开发者设置在完整工作台中。','You can look up products here. Favorites, customization projects, AI chat and Developer settings are in the full workbench.')}</p>`+
      `<p>${t('首次使用完整工作台，请安装 64 位 Python 3.12 或 3.13，将 ZIP「全部解压」，再双击','For the full workbench, install 64-bit Python 3.12 or 3.13, extract the entire ZIP, then double-click')} <strong>${t('启动助手.cmd','Start Assistant.cmd')}</strong>${t('。如果启动器提示找不到 Python，请按安装说明操作；现在也可以直接在下方查商品。',' in the extracted folder. If the launcher cannot find Python, follow the setup guide. You can already search for products below.')}</p></div>`+
      `<div class="preview-guide-actions"><a class="workbench-link" href="${h(workspaceLink())}">${t('打开已启动的工作台','Open a running workbench')} ↗</a><small>${t('默认端口 8765；其他端口以启动器为准。','Default port 8765. Use the launcher’s address if it differs.')}</small><div>${link(docs,t('安装说明','Setup guide'))} · <a href="?lang=${locale}${h(location.hash)}" lang="${locale}">${lang==='en'?'简体中文':'English'}</a></div></div></section>`;
  }
  function shell(){
    historyControls();
    document.documentElement.lang=lang;document.title=t('Seeed Studio · L1轻定制小助手','Seeed Studio · L1 Light Customization Assistant');
    document.querySelector('.app-name').textContent=t('L1轻定制小助手','L1 Light Customization Assistant');
    el('mode-name').textContent=connected?t('完整本地工作台','Full local workbench'):t('只读目录预览','Read-only catalogue');
    el('nav').setAttribute('aria-label',t('工作区','Workspace'));
    const entries=[['assistant','⌕',t('选型查询','Product finder')],['catalog','▦',t('产品目录','Catalogue')],['favorites','☆',t('我的收藏','Favorites')],['custom','▧',t('定制服务','Customization')],['coverage','▤',t('采集概况','Coverage')]];
    el('nav').innerHTML=entries.filter(([id])=>connected||!['favorites','custom'].includes(id)).map(([id,icon,name])=>`<button data-view="${id}" aria-current="${id===state.view?'page':'false'}"><span aria-hidden="true">${icon}</span>${h(name)}</button>`).join('');
    el('developer-link').innerHTML='<span aria-hidden="true">⚙</span> '+t('开发者','Developer');
    el('developer-link').hidden=!connected;
    el('developer-link').setAttribute('aria-current',state.view==='developer'?'page':'false');
    el('store-link').textContent=t('Seeed Studio 海外商城 ↗','Seeed Studio store ↗');
    el('service-status').innerHTML=connected?'':previewGuide();
    if(connected)window.Workbench?.sidebarFavorites();
    else el('sidebar-favorites').replaceChildren();
  }
  function queryForm(){
    const samples=lang==='en'?['J4012, need Super mode','R1100 with EU868','Industrial gateway with RS485 and DIN rail']:['J4012 需要 Super 模式','R1100，客户需要 EU868','工业网关，需要 RS485 和导轨'];
    const label=t('输入型号、SKU 或客户需求','Enter a model, SKU or customer requirement');
    return `<form id="ask" class="ask"><span aria-hidden="true">⌕</span><input id="asktext" aria-label="${h(label)}" placeholder="${h(label)}" value="${h(state.query)}"><button>${t('查询','Search')}</button></form>
      <div class="examples"><span>${t('试一试','Try')}</span>${samples.map(s=>`<button data-example="${h(s)}">${h(s)}</button>`).join('')}
      <details class="rule-help"><summary>${t('查询与推荐规则','How matching works')}</summary><p>${t('指定 SKU 优先，其次匹配产品名称和版本。只给系列时会标明代表配置。其他需求按接口、应用和英文关键词查找；已识别的否定条件不计为必需。相似项参考同系列、品类、名称特征及需求差异。具体参数引用对应型号的官方 Wiki 或商品页。','An exact SKU has priority, then a named product or variant. A family-only match shows a representative configuration. Interface, application and English keywords inform other matches; recognized negations are excluded. Alternatives are ranked by family, category, shared terms and requested differences. Technical facts link to the applicable Wiki or store page.')}</p></details></div>`;
  }
  function mainCard(p,result){
    const conflict=p.series==='classic'&&result.needs.some(t=>t.key==='super');
    const terms=[p.bundle,...(p.capabilities||[])].filter(Boolean).map(local);
    const missing=(p.missingSummary||p.notes.filter(n=>n.kind==='另购说明').slice(0,2).map(n=>n.text)).map(local);
    const description=state.pin?t('指定产品','Selected product'):result.selection||(result.explicit?t('指定产品','Selected product'):t('需求匹配结果','Requirement match'));
    const proof=connected?window.Workbench.customizationInfo(p):null;
    const serviceMention=p.notes.find(n=>n.kind==='定制说明'&&n.source);
    const custom=proof?.text||(p.custom&&p.customUrl?local(p.custom):serviceMention?t('官方资料提及定制服务，适用范围待核','Customization service mentioned; scope needs confirmation'):'');
    const customSource=proof?proof.url:p.customUrl||serviceMention?.source;
    const optionGroups=productOptions(p),options=optionGroups.filter(g=>g.items.length&&!offerOnly(g)),offerCount=optionGroups.filter(offerOnly).length;
    const interfaces=options.filter(g=>g.items.every(a=>a.type==='Expansion interface')).length;
    const optionCount=options.length?(interfaces===options.length?t(interfaces+' 个扩展接口',interfaces+' expansion interfaces'):t(options.length+' 项配件或扩展',options.length+' accessories or expansions')):optionGroups.some(g=>!offerOnly(g))?t('查看定制或另购说明','View customization or exclusions'):t('暂无已核条目','No verified items');
    const attrs=p.attributes||[];
    const modelSpecs=p.modelSpecs||[];
    const fields=attrs.length?attrs:modelSpecs;
    const highlights=['RAM','Storage','Operating System','Network'].map(name=>fields.find(a=>a.name===name)).filter(Boolean).slice(0,3);
    return `<section class="panel selected"><div class="card-top"><div class="section-label"><i></i>${h(description)}</div>${connected&&window.Workbench?window.Workbench.productActions(p.sku):''}</div>
      ${p.url?`<div class="product-url">${link(p.url,p.url)}</div>`:''}
      <div class="hero-product">${photo(p,'hero-photo')}<div><div class="eyeline">${h(p.groups[0]||p.paths[0]?.[0]||(p.isLocal?t('本地产品','Local product'):t('海外商城','Global store')))}</div>
      <h2>${productLabel(p,short(p))}</h2>${short(p)!==p.name?`<div class="official-name">${productLabel(p,p.name,false)}</div>`:''}<div class="item-sku">SKU <b>${productLabel(p,p.sku,false)}</b></div><div class="hero-price">${h(price(p))}</div>
      ${p.updated?`<span class="date">${t('商城快照','Store snapshot')} · ${h(p.updated)}</span>`:''}
      ${p.stockStatus&&p.storePageStatus!=='not_found'?`<span class="date"> · ${h(({IN_STOCK:t('官网有货','In stock'),OUT_OF_STOCK:t('官网无货','Out of stock')})[p.stockStatus]||p.stockStatus)}</span>`:''}
      ${p.storeLifecycle?`<span class="date"> · ${t('官网生命周期','Store lifecycle')} ${h(p.storeLifecycle)} ${p.lifecycleSource?link(p.lifecycleSource,t('来源 ↗','Source ↗')):''}</span>`:''}
      ${p.catalogStatus==='retained_previous'?`<span class="date"> · ${t('保留的历史 SKU','Retained from an earlier catalogue')}</span>`:''}</div></div>
      ${/^(?:eol|end[ -]of[ -]life|discontinued)$/i.test(p.storeLifecycle||'')?`<p class="warn">${t('官网将这款产品标为停产。报价前请核实剩余库存或替代型号。','The store marks this product as end of life. Confirm remaining stock or a replacement before quoting.')}</p>`:''}
      ${window.InternalUI?.product(p,lang,'summary')||''}
      ${p.isInternal?`<p class="caption">${t('此 SKU 仅见于本机内部资料，商城商品身份尚未确认。','This SKU appears in local internal documents. Its store identity is unconfirmed.')}</p>`:''}
      ${p.catalogStatus==='live_secondary'?`<p class="warn">${p.storePageStatus==='not_found'?t('站点地图留档。商城路由仍返回该 SKU，商品页本轮返回 HTTP 404，价格与供货需另行确认。','Sitemap record. The store routing service still returns this SKU, but the product page returned HTTP 404 in this review. Confirm price and availability separately.'):t('该 SKU 来自官网站点地图和商品路由，未出现在公开搜索目录中。报价前请确认供货状态。','This SKU was found in the official sitemap and routing data and is absent from public product search. Confirm availability before quoting.')} ${link(db.audit?.sources?.sitemap,t('官网站点地图 ↗','Official sitemap ↗'))}</p>`:''}
      ${/^DETAIL_.*(?:SKU|ID).*VERIF/i.test(p.detailAudit?.error||'')?`<p class="warn">${t('本次打开该网址时，未能确认页面对应此 SKU。请按 SKU 核对目录记录与所引手册。','This product page could not be verified as the same SKU. Check the SKU in the catalogue record and the cited documentation.')} ${landingEvidence(p)}</p>`:''}
      ${terms.length?`<div class="tokens">${terms.map(s=>`<span>${h(s)}</span>`).join('')}</div>`:''}
      ${highlights.length?`<div class="spec-highlights">${highlights.map(a=>`<span><small>${h(attributeLabel(a.name))}</small> ${h(a.value)}</span>`).join('')}</div>`:''}
      ${missing.length?`<div class="missing-line"><b>${t('需另购 / 不随箱','Sold separately')}</b><span>${h(missing.join(lang==='en'?', ':'、'))}</span><button class="textbtn" data-tab="accessories">${t('查看依据','Evidence')} ›</button></div>`:''}
      ${conflict?`<p class="warn"><b>${t('需求差异','Requirement gap')}</b> ${t('这个 Classic 版本不支持 Super 模式。请比较右侧的 Super J4012。','This Classic version does not support Super mode. Compare the Super J4012 in alternatives.')}</p>`:''}
      <div class="detail-key"><div><small>${t('定制范围','Customization')}</small><div>${h(custom)}</div>${customSource?link(customSource,t('查看来源 ↗','Source ↗')):''}${serviceMention&&!proof?` <button class="textbtn" data-tab="accessories">${t('查看说明','Details')} ›</button>`:''}</div>
      <div><small>${t('技术规格','Specifications')}</small><button class="textbtn" data-tab="specs">${t('查看规格与型号配置','View specs and model details')} ›</button></div>
      <div><small>${t('箱内清单','In the box')}</small><button class="textbtn" data-tab="parts">${p.parts.length?t(p.parts.length+' 项随附',p.parts.length+' included'):recordLabel(p.partStatus)} ›</button></div>
      <div><small>${t('配件与定制','Accessories & customization')}</small><button class="textbtn" data-tab="accessories">${optionCount} ›</button>${offerCount?`<small>${t('另有 '+offerCount+' 个商城加购项',offerCount+' store add-on offers')}</small>`:''}</div></div>
      ${p.sharedUrl?`<small>${t('多个 SKU 共用上述商品页。','Multiple SKUs share this product page.')}</small>`:''}
      ${p.summary||p.storeFeatures?.length||p.storeApplications?.length?`<details class="summary"><summary>${p.isEdited?t('产品简介','Product summary'):t('官网产品简介','Store summary')}</summary>${p.summary?`<p>${h(p.summary)}</p>`:''}${listed(t('官网特性','Store features'),p.storeFeatures)}${listed(t('应用场景','Applications'),p.storeApplications)}</details>`:''}</section>`;
  }
  function facts(p){
    const e=p.wikiEvidence?.[0];
    if(e)return `<section class="panel evidence-panel"><div class="section-label">${t('选型依据','Selection evidence')}</div><p>${h(e[lang==='en'?'en':'zh'])}</p>${link(e.url,'Seeed Wiki · '+e.scope+' ↗','source-link')}</section>`;
    const kinds={exclusion:t('另购 / 不随箱','Sold separately'),expansion:t('扩展接口','Expansion interface'),modelSpec:t('型号参数','Model specification'),accessory:t('手册列出的配件','Documented accessory'),inbox:t('随箱物料','In-box item'),customization:t('定制服务','Customization')};
    const verified=(p.verifiedDocumentRows||[]).filter(r=>kinds[r.kind]&&r.source);
    if(verified.length){
      const order=Object.keys(kinds),rows=[...verified].sort((a,b)=>order.indexOf(a.kind)-order.indexOf(b.kind)).slice(0,2);
      return `<section class="panel evidence-panel"><div class="section-label">${t('选型依据','Selection evidence')}</div>${rows.map(r=>`<p>${h(kinds[r.kind])} · ${h([r.name,r.value,r.quantity?'× '+r.quantity:''].filter(Boolean).join(' '))} ${evidenceLink(r.source)}</p>`).join('')}</section>`;
    }
    const none=p.isLocal?t('该 SKU 来自本地人工记录，尚无经核对的 Wiki 结论。','This SKU is a local record. It has no verified Wiki finding.'):t('尚无经核对的型号 Wiki 结论。可从商品页核对规格。','No model-specific Wiki finding has been verified. Check the product specifications on the store page.');
    return `<section class="panel evidence-panel"><div class="section-label">${t('选型依据','Selection evidence')}</div><p>${none}</p>${link(p.url,t('商品链接 ↗','Product link ↗'),'source-link')}${p.wikiLinks?.length?` <button class="textbtn" data-tab="docs">${t('查看关联 Wiki','Linked Wiki resources')} ›</button>`:''}</section>`;
  }
  function related(p,rec){
    return `<section class="panel related"><div class="section-label">${t('相似与替代产品','Alternatives')}</div>${rec.length?rec.map(({p:a,why})=>{
      const source=a.wikiEvidence?.[0];
      return `<div class="rec">${photo(a)}<div>${productLink(a,short(a),'rec-name')}<p>${h(why)}</p><span class="rec-price">${h(price(a))}</span> ${link(source?.url,'Wiki ↗','source-link')} ${link(a.url,t('商品页 ↗','Store ↗'),'source-link')}</div></div>`;
    }).join(''):`<p class="secondary">${t('没有找到有依据的相似项。','No supported alternative found.')}</p>`}</section>`;
  }
  const attributeNames={'Product Type':'产品类型','Categories':'分类','Sensors':'传感器','Series':'系列','RAM':'内存（RAM）','Storage':'存储','Operating System':'操作系统','Network':'网络','Interface':'接口','Connectivity':'连接方式'};
  const attributeLabel=name=>lang==='en'?name:attributeNames[name]||name;
  const recordLabel=status=>status==='empty'?t('已查栏目未列出','No entry in checked section'):status==='unparsed'?t('待核对原文','Review source'):t('待核对','Pending verification');
  const listed=(name,values)=>values?.length?`<b>${h(name)}</b><ul>${values.map(x=>`<li>${h(x)}</li>`).join('')}</ul>`:'';
  const numberOfRows=(tables,text)=>(tables||[]).reduce((count,table)=>count+table.rows.length,0)+(text?.length||0);
  const specCount=p=>numberOfRows(p.specTables,p.specText)+numberOfRows(p.referenceSections?.certification_info_tech?.tables,p.referenceSections?.certification_info_tech?.text);
  const canonicalTab=tab=>tab==='attributes'?'specs':tab==='notes'?'accessories':tab;
  const defaultTab=p=>p.isInternal?'docs':p.attributes?.length||p.modelSpecs?.length||!p.parts?.length&&specCount(p)?'specs':'parts';
  const tabs=p=>({specs:t('技术规格','Specifications'),parts:t('箱内清单','In the box'),accessories:t('配件与定制','Accessories & customization'),...(p.unclassifiedRows?.length?{raw:t('原表待核','Rows to review')}:{}),docs:t('文档与来源','Documents & sources')});
  function storeSpecifications(p){
    const statuses={empty:t('已查阅该 SKU 的 Specification 栏，官网未列正文。','The checked Specification section contains no text.'),image:t('原站以图像或嵌入内容展示规格，可打开原文查看。','The store presents specifications as images or embedded content. Open the source to inspect them.'),unparsed:t('已读取该栏目，原文格式需要复核。','The section was retrieved. Its source format needs review.')};
    const count=numberOfRows(p.specTables,p.specText),source=evidenceLink(p.specSource||p.url);
    const extra=referenceSections(p,['certification_info_tech','hardware_overview']);
    if(!count)return (extra||`<div class="record-empty"><p>${h(statuses[p.specStatus]||t('此 SKU 的技术规格栏目尚未核对。','The Specification section has not been checked for this SKU.'))}</p>${source}</div>`);
    const omitted=p.specRowsOmitted?t('另有 '+p.specRowsOmitted+' 段或行需在原文查看。',p.specRowsOmitted+' additional blocks or rows are available in the source.'):'';
    const origin=p.specLocation==='description'?t('来源为商品正文中的规格小节。','From the specifications in the product description.'):t('来源为商品的 Specification 专栏。','From the dedicated store Specification section.');
    return `<p class="caption">${origin} ${t('对照表中请读取对应型号一列。','In comparison tables, read the column for your model.')} ${h(omitted)} ${source}</p>${officialTables(p.specTables)}${listed(t('官网说明','Store notes'),p.specText)}${extra}`;
  }
  function modelDetails(p){
    const raw=p.attributes||[],model=p.modelSpecs||[];
    if(!raw.length&&!model.length)return '';
    const fields=raw.length?raw:model;
    const label=raw.length?t('商品页 Part List 中的型号参数','Model parameters in the store’s Part List'):t('已核型号配置','Verified model configuration');
    const corroboration=raw.length&&model.length?`<p class="caption">${t('其他型号依据','Additional model evidence')} · ${model.map(a=>h(attributeLabel(a.name)+' '+a.value)+' '+evidenceLink(a.source||p.url)).join(' · ')}</p>`:'';
    return `<section class="model-details"><h3>${label}</h3>`+
      table([t('参数','Parameter'),t('本型号的值','Value for this model'),t('依据','Source')],fields.map(a=>[h(attributeLabel(a.name))+(attributeLabel(a.name)!==a.name?`<small>${h(a.name)}</small>`:'')+(a.group?`<small>${h(a.group)}</small>`:''),h(a.value),evidenceLink(a.source||p.attributeSource||p.url)]))+corroboration+'</section>';
  }
  function officialTables(tables){
    return (tables||[]).map(({title,rows})=>{
      const body=rows.map(row=>'<tr>'+row.map(cell=>{
        const entry=typeof cell==='object'?cell:{text:cell};
        const tag=entry.header?'th':'td';
        const spans=['rowspan','colspan'].filter(key=>Number.isInteger(entry[key])&&entry[key]>1&&entry[key]<=200).map(key=>' '+key+'="'+entry[key]+'"').join('');
        const uncertain=entry.unconfirmed?`<small>${t('官网以零值占位，尺寸待核','All-zero source value; dimensions unconfirmed')}</small>`:'';
        return '<'+tag+spans+'>'+h(entry.text)+uncertain+'</'+tag+'>';
      }).join('')+'</tr>').join('');
      return `<div class="table-scroll official-specs"><table>${title?`<caption>${h(title)}</caption>`:''}<tbody>${body}</tbody></table></div>`;
    }).join('');
  }
  function referenceSections(p,keys){
    const titles={certification_info_tech:t('技术参数附表','Technical details'),hardware_overview:t('硬件概览','Hardware overview'),certification_info:t('商品页认证栏目','Store certification section'),certification_info_eccn:t('商品页编码栏目','Store classification codes'),faq_list:t('常见问题','FAQ')};
    return keys.filter(k=>p.referenceSections?.[k]).map(k=>{
      const s=p.referenceSections[k];
      return `<section><h3>${titles[k]}</h3><p class="caption">${s.mediaOnly?t('此栏以图示展示，见商品页。','This section uses images; see the product page.')+' ':''}${evidenceLink(s.source||p.url)}</p>${officialTables(s.tables)}${listed(t('官网说明','Store notes'),s.text)}</section>`;
    }).join('');
  }
  function evidenceLabel(url){
    if(/\/\/wiki\.seeedstudio\.com\//i.test(url))return t('官网 Wiki','Official Wiki');
    if(/\/\/github\.com\/Seeed-Studio\/wiki-documents\/blob\//i.test(url))return t('官方 Wiki 源文件','Official Wiki source');
    if(/\.pdf(?:[?#]|$)/i.test(url)){
      const page=url.match(/#page=(\d+)/i)?.[1];
      return page?t('PDF 第 '+page+' 页','PDF page '+page):t('官方手册','Official manual');
    }
    return t('商品页','Store page');
  }
  const evidenceLink=url=>url?link(url,evidenceLabel(url)+' ↗'):'';
  function emptyPackingList(p){
    const status=p.partStatus;
    let explanation;
    if(p.isLocal)explanation=t('这是本地新增产品，暂无已核实的官网记录。','This local product has no verified store record.');
    else if(status==='empty')explanation=t('已核对的商品栏目未列出随箱物料。型号参数请查看「技术规格」，另购件请查看「配件与定制」。','The checked store section lists no in-box items. See Specifications for model details and Accessories & customization for optional items.');
    else if(status==='unparsed')explanation=t('已读取官网栏目，原文格式仍需核对。','The store section was retrieved. Its contents still need review.');
    else explanation=t('此 SKU 的随箱物料尚待核对。请查看商品页或官方手册。','The package contents for this SKU are pending verification. Check the product page or manual.');
    return `<div class="record-empty"><p>${h(explanation)}</p>${p.unclassifiedRows?.length?`<button class="textbtn" data-tab="raw">${t('查看待核的官网原表行','View original rows awaiting review')} ›</button> · `:''}${evidenceLink(p.partSource||p.url)}</div>`;
  }
  let optionCache;
  function productOptions(p){
    if(optionCache?.product===p&&optionCache.search===search)return optionCache.groups;
    const services=[];
    const official=p.isEdited?base.products.find(item=>item.sku===p.sku):p;
    if(official?.custom&&official.customUrl)services.push({kind:t('系列定制','Family customization'),text:local(official.custom),url:official.customUrl});
    const proof=connected?window.Workbench.customizationInfo(p):null;
    if(proof&&!services.some(s=>s.text===proof.text&&s.url===proof.url))services.push(proof);
    const groups=accessoryGroups(p,services,item=>item.publishedSku&&!item.sku&&p.documentConflicts?.some(c=>c.publishedSku===item.publishedSku)?null:search.accessoryMatch(item));
    optionCache={product:p,search,groups};return groups;
  }
  function optionType(a){
    if(a.documentedAsAccessorySource)return t('官方文档列明的配件','Documented accessory');
    return ({'Expansion interface':t('扩展接口','Expansion interface'),'Official accessory list':t('官方文档列明的配件','Documented accessory'),'Official compatibility list':t('官方兼容清单','Official compatibility list'),'Official module list':t('官方模组清单','Official module list'),'商品页标明选配':t('商品页标明选配','Optional on the store page')})[a.type]||local(a.type);
  }
  const offerOnly=g=>g.items.length>0&&g.items.every(storeOffer)&&!g.notes.length&&!g.services.length;
  function matchingOptions(p){
    const groups=productOptions(p),q=state.accFilter.trim();
    if(!q)return groups;
    return groups.filter(g=>catalogTextMatches(q,g.match?.product?.name,g.match?.product?.sku,
      ...g.items.flatMap(a=>[a.name,a.storeName,a.sku,a.publishedSku,a.type,optionType(a),a.note,local(a.note),a.scope,
        ...(bazaarAccessoryCheck(a)?.candidates||[]).flatMap(c=>[c.name,c.sku]),
        ...(a.compatibilityDetails||[]).flatMap(c=>[c.interface,c.voltage,c.makeCode])]),
      ...g.notes.flatMap(n=>[n.kind,n.text,local(n.kind),local(n.text)]),...g.services.flatMap(s=>[s.kind,s.text])));
  }
  function optionRow(g){
    const target=g.match?.product,first=g.items[0],name=first?.name||first?.storeName||local(g.notes[0]?.text)||g.services[0]?.text||'';
    const details=new Set(),sources=new Map(),names=new Set([name]);
    const add=(set,value)=>{if(value)set.add(value);};
    const cite=(url,label)=>{
      if(!safe(url))return;
      if(!sources.has(url))sources.set(url,new Set());
      sources.get(url).add(label||evidenceLabel(url));
    };
    for(const a of g.items){
      add(names,a.name);add(names,a.storeName);
      const scope=a.scope?(a.scope==='sku'?t('本型号','SKU scope'):a.scope==='family'||a.scope.includes('_')?t('系列资料','Family documentation'):t(a.scope+' 系列资料',a.scope+' family documentation')):'';
      add(details,h([scope,optionType(a),local(a.note)].filter(Boolean).join(' · ')));
      const doc=db.docs[a.doc];
      if(doc&&a.page)cite(doc.url+'#page='+a.page);
      cite(a.source,storeOffer(a)||a.documentedAsAccessorySource?t('商城加购','Store add-on'):'');
      cite(a.documentedAsAccessorySource);
      for(const source of [a.notIncludedSource,a.soldSeparatelySource])if(source){
        add(details,h(t('另购 / 不随箱','Sold separately / not included')));
        cite(source,t('另购依据','Sold-separately evidence'));
      }
      for(const d of a.compatibilityDetails||[]){
        add(details,h([d.interface,d.voltage,d.makeCode?'MakeCode · '+d.makeCode:'',d.sheet&&d.row?d.sheet+' · '+t('第 '+d.row+' 行','Row '+d.row):''].filter(Boolean).join(' · ')));
        cite(d.source);
      }
      const check=bazaarAccessoryCheck(a);
      if(check){
        const labels={confirmed:t('商城已核对商品身份','Store identity verified'),candidates:t('商城候选，型号与兼容性待核','Store candidates; verify model and compatibility'),
          not_found:t('商城检索未返回对应商品','No item returned by the store search'),
          no_title_match:t('已读取的商城结果中未找到对应型号','No matching title in the inspected store results'),
          needs_specification:t('需补充规格后确认商品','Specifications required to identify an item'),
          source_error:t('商城核查读取失败，保留原记录','Store check failed; original record retained'),
          excluded:t('商城抓取规则限制，保留原记录','Store rules restricted this check'),
          rate_limited:t('商城限速，本次核查待续跑','Store rate limit; check pending')};
        add(details,h([labels[check.status]||t('商城核查待完成','Store check pending'),(check.checkedAt||'').slice(0,10)].filter(Boolean).join(' · ')));
        const candidateCheck=check.status==='candidates'?check:check.lastSuccessful?.status==='candidates'?check.lastSuccessful:null;
        if(candidateCheck){
          for(const candidate of candidateCheck.candidates||[]){
            if(/^https:\/\/www\.seeedstudio\.com\/[^\s]*\.html$/i.test(candidate.url||'')){
              add(details,link(candidate.url,candidate.name+' · SKU '+candidate.sku+' ↗'));
            }
          }
        }
      }
    }
    for(const n of g.notes){
      const note=local(n.text);
      const scope=n.scope?(n.scope==='sku'?t('本型号','SKU scope'):n.scope==='family'?t('系列资料','Family documentation'):t(n.scope+' 系列资料',n.scope+' family documentation')):'';
      add(details,h([scope,local(n.kind),names.has(note)?'':note].filter(Boolean).join(' · ')));
      cite(n.source,local(n.where));
    }
    for(const s of g.services){
      add(details,h([s.kind,names.has(s.text)?'':s.text].filter(Boolean).join(' · ')));
      cite(s.url,t('定制依据','Customization evidence'));
    }
    for(const match of g.matches){
      if(match.method==='successor'){
        add(details,h(t('商城后继款（GA → GR），替换前请确认项目适用性。','Store successor (GA → GR). Confirm suitability before substitution.')));
        cite(match.source,t('原厂替代通知','Manufacturer change notice'));
      }else if(match.method!=='sku'&&match.source!==target?.url)cite(match.source,t('型号核对','Model evidence'));
      if(match.skuSource!==target?.url)cite(match.skuSource,t('商城 SKU 依据','Store SKU evidence'));
    }
    const titles=[...names].map((value,index)=>{const text=target?productLabel(target,value,false):h(value);return index?'<small>'+text+'</small>':'<b>'+text+'</b>';}).join('');
    const published=first?.publishedSku||first?.sku;
    const identifier=target?(target.isExternal?h(target.sku):productLink(target)):h(published)+(published?`<small>${t('来源编号，尚无可核的商城商品','Source identifier; no confirmed store product')}</small>`:'');
    const sourceLink=(url,labels)=>link(url,[...labels].join(' · ')+' ↗');
    let store='';
    if(target?.url){
      const labels=sources.get(target.url)||new Set();labels.add(t('商品页','Store page'));
      store=sourceLink(target.url,labels);sources.delete(target.url);
    }
    return [titles+[...details].map(d=>'<small>'+d+'</small>').join(''),identifier,store,[...sources].map(([url,labels])=>sourceLink(url,labels)).join('<br>')];
  }
  function optionsTable(p){
    const groups=matchingOptions(p),offers=groups.filter(offerOnly),other=groups.filter(g=>!offerOnly(g));
    const columns=[t('商品、定制及适用条件','Item, customization and conditions'),'SKU',t('商城','Store'),t('依据','Source')];
    const list=items=>table(columns,items.map(optionRow));
    const empty=state.accFilter?t('没有符合此筛选的记录。','No records match this filter.'):t('尚无已核实的配件、扩展或定制记录。','No accessory, expansion or customization records have been verified.');
    return `<div class="list-tools"><input id="accfilter" aria-label="${t('筛选配件与定制','Filter accessories and customization')}" placeholder="${t('名称、接口、频段、定制或 SKU','Name, interface, band, service or SKU')}" value="${h(state.accFilter)}"><span>${groups.length} ${t('个匹配项','matches')}</span></div>`+
      documentConflicts(p)+(other.length?list(other):'')+
      (offers.length?`<details class="summary" data-nav-disclosure="offers" data-offer-sku="${h(p.sku)}"${offersExpanded(p.sku)?' open':''}><summary>${t('商品页同时推荐加购','Also Add offers from the store')} · ${num(offers.length)}</summary><p class="caption">${t('商城在同一商品页推荐加购。选型时请另行核实兼容条件。','The store suggested these items on the same page. Check compatibility for the intended configuration.')}</p>${list(offers)}</details>`:'')+
      (!groups.length?`<p class="record-empty">${empty} ${state.accFilter?'':evidenceLink(p.url)}</p>`:'')+(window.InternalUI?.product(p,lang,'options')||'');
  }
  function information(p){
    const counts={specs:specCount(p)+(p.attributes?.length||p.modelSpecs?.length||0),parts:p.parts.length,raw:p.unclassifiedRows?.length,accessories:productOptions(p).length,docs:new Set([...p.docs.map(d=>d.url),...(p.wikiLinks||[]).map(d=>d.url),...(p.wikiEvidence||[]).map(d=>d.url)]).size};
    const active=state.tab||defaultTab(p);
    return `<section class="panel information"><div class="tabs" role="tablist">${Object.entries(tabs(p)).map(([id,name])=>`<button role="tab" data-tab="${id}" aria-selected="${active===id}">${h(name)}${counts[id]?`<sup>${counts[id]}</sup>`:''}</button>`).join('')}</div><div id="tabbody" role="tabpanel">${tabBody(p)}</div></section>`;
  }
  function tabBody(p){
    const active=state.tab||defaultTab(p);
    if(active==='specs')return modelDetails(p)+storeSpecifications(p)+(window.InternalUI?.product(p,lang,'specs')||'');
    if(active==='raw'){
      return `<p class="caption">${t('官网栏目包含下列原文，尚待确认它们是随附物料、规格还是其他说明。','These original store rows require review before they can be classified as included items, specifications or other information.')} ${evidenceLink(p.unclassifiedSource||p.url)}</p>`+
        table([t('官网原文','Original store text')],(p.unclassifiedRows||[]).map(row=>[h(Array.isArray(row)?row.join(' · '):row)]));
    }
    if(active==='parts'){
      if(!p.parts.length)return documentConflicts(p,true)+emptyPackingList(p);
      const doc=db.docs[p.partDoc];
      const noQty=p.parts.some(([,q])=>!q);
      const family=p.partEvidenceScope==='family'?t('以下随附物料来自官方系列资料。','The following included items are documented at the product-family level.'):p.partEvidenceScope==='mixed'?t('已合并本型号商品页与官方系列资料，依据逐项标注。','Includes SKU-specific and family-level records. Each row identifies its source.'):'';
      const quantityNote=noQty?t('数量留空表示原文未披露，或不同记录尚不足以确定总数。','A blank quantity means the source gives no count or the total could not be verified across records.'):'';
      const conflictRows=new Map();
      const addConflict=(name,quantity,source)=>{
        const count=String(quantity||'').trim().replace(/^[×x]\s*(?=\d)/i,'');
        conflictRows.set(JSON.stringify([String(name).trim().toLowerCase(),count,source]),[h(name),h(quantity),evidenceLink(source)]);
      };
      for(const c of p.partConflicts||[]){addConflict(c.name,c.existingQuantity,c.existingSource);addConflict(c.name,c.documentQuantity,c.documentSource);}
      for(const [name,records] of Object.entries(p.partQuantityConflicts||{}))for(const item of records)addConflict(name,item.quantity,item.source);
      const discrepancy=conflictRows.size?`<p class="warn">${t('以下物料的官方数量存在差异，报价前请核实。','Official sources disagree on these quantities. Confirm before quoting.')}</p>${table([t('物料','Item'),t('各来源记录的数量','Quantity in each source'),t('依据','Source')],[...conflictRows.values()])}`:'';
      const alternate=(p.alternatePackingLists||[]).map(list=>{
        const internal=list.kind==='assembly_components';
        const label=internal?t('商城列出的装机组成','Installed components listed by the store'):list.kind==='document'?t('手册列出的同一包装清单','Document list for the same package'):t('商城按总成列出的同一包装清单','Storefront list for the same package, grouped by assembly');
        const note=internal?t('这些部件属于主机组成。独立发货件数以随箱清单为准。','These components are installed in the host. Use the packing list for the separately shipped items.'):t('请按一种口径核数，商城清单与手册行数可有差异。','Count against one source. The store and the manual may group the same components differently.');
        return `<details class="summary"><summary>${label}</summary><p class="caption">${note} ${evidenceLink(list.source)}</p>${table([t('原文物料名称','Original item name'),t('数量','Quantity'),t('依据','Source')],list.parts.map(([name,quantity])=>[h(name),h(quantity),evidenceLink(list.partSources?.[name]||list.source)]))}</details>`;
      }).join('');
      const packingRows=p.parts.map(([name,quantity])=>{
        const note=p.partDescriptions?.[name],source=p.partSources?.[name]||p.partSource||(doc?doc.url+'#page=1':p.url);
        const notePrefix=note?.kind==='alias'?t('其他官方资料用名：','Also listed as '):note?.kind==='configuration'?t('商城列出的系列选项：','Family options listed by the store: '):note?.kind==='crossListed'?t('该物料在多个分类重复列出，实际总数待核。','The item is printed in multiple categories. Its total quantity needs confirmation. '):'';
        const noteText=note?.text?notePrefix+note.text:'';
        const description=noteText?`<small>${h(noteText)} ${note.source&&note.source!==source?evidenceLink(note.source):''} ${note.crosscheck?link(note.crosscheck,t('手册核对 ↗','Manual confirmation ↗')):''}</small>`:'';
        const published=p.partPublishedSkus?.[name];
        const disputed=published&&p.documentConflicts?.some(c=>c.publishedSku===published);
        const match=disputed?null:search.accessoryMatch({name,source,sku:p.partProductSkus?.[name],publishedSku:published}),target=match?.product;
        const replacement=match?.method==='successor'?t('商城后继款','Store successor')+' · ':'';
        const itemLink=target&&target.sku!==p.sku?`<small>${h(replacement)}${productLink(target,'SKU '+target.sku)} · ${link(target.url,t('商城 ↗','Store ↗'))}${match.source&&match.source!==source&&match.source!==target.url?' · '+link(match.source,t('型号依据 ↗','Model evidence ↗')):''}</small>`:published?`<small>${h(t('文件货号 ','Published SKU ')+published)}</small>`:'';
        const precise=p.partSourceLocations?.[name];
        const location=precise?`<small>${h([precise.sheet,precise.cellRange||t('第 '+precise.row+' 行','Row '+precise.row)].filter(Boolean).join(' · '))}</small>`:'';
        const qtySource=p.partQuantitySources?.[name],qtyLink=qtySource&&qtySource!==source?'<small>'+link(qtySource,t('数量依据 ↗','Count source ↗'))+'</small>':'';
        const more=(p.partOtherSources?.[name]||[]).filter(url=>url!==source&&url!==note?.crosscheck&&url!==qtySource).map((url,i)=>link(url,t('交叉依据 ','Additional source ')+(i+1)+' ↗')).join(' · ');
        return [h(name)+itemLink+description,h(quantity)+qtyLink,evidenceLink(source)+location+(p.partScopes?.[name]==='family'?`<small>${t('系列资料','Family scope')}</small>`:'')+(more?'<small>'+more+'</small>':'')];
      });
      return (family||quantityNote?`<p class="caption">${h([family,quantityNote].filter(Boolean).join(' '))}</p>`:'')+
        documentConflicts(p,true)+discrepancy+table([t('随箱物料','Included item'),t('数量','Quantity'),t('依据','Source')],packingRows)+alternate;
    }
    if(active==='accessories')return optionsTable(p);
    const rows=[[h(p.name),link(p.url,t('海外商城 ↗','Global store ↗'))]];
    if(p.image||p.imageUrl)rows.push([t('产品主图','Product photo'),[link(p.image,t('本地主图 ↗','Local image ↗')),link(p.imageUrl,t('官网图源 ↗','Store image ↗'))].filter(Boolean).join(' · ')]);
    const seen=new Set();
    for(const e of p.wikiEvidence||[]){rows.push([h(e.title),link(e.url,t('已核对的 Wiki ↗','Verified Wiki ↗'))]);seen.add(e.url);}
    for(const d of p.docs){if(!seen.has(d.url)){rows.push([h(d.name),link(d.url,t('打开原文 ↗','Open source ↗'))]);seen.add(d.url);}}
    for(const w of p.wikiLinks||[])if(!seen.has(w.url)){
      const reverse=w.relation==='purchase_link'||w.relation==='declared_sku';
      const label=w.declaredSku?t('Wiki 明确列出此 SKU ↗','Wiki explicitly lists this SKU ↗'):reverse?t('Wiki 中此 SKU 的购买入口 ↗','Wiki with purchase link to this SKU ↗'):t('商品页随附 Wiki ↗','Wiki linked by store ↗');
      const revision=w.source+(w.metadataLine?'#L'+w.metadataLine:'');
      const scope=w.sourceScope==='application'?t('应用教程','Application guide'):w.sourceScope==='multi_sku'?t('本页涉及多个 SKU','Covers multiple SKUs'):w.sourceScope==='component_guide'?t('部件指南，整套配置另核','Component guide, check kit contents separately'):'';
      rows.push([h(w.title)+(scope?'<small>'+h(scope)+'</small>':''),link(w.url,label)+(reverse&&w.source?' · '+link(revision,t('官方源码 ↗','Source revision ↗')):'')]);seen.add(w.url);
    }
    const relationNames={related:t('商城相关商品','Store-related product'),upsell:t('商城升级推荐','Suggested upgrade'),crosssell:t('商城搭配推荐','Store cross-sell')};
    for(const relation of p.storeRelations||[]){
      const target=search.bySku.get(String(relation.sku).toLowerCase());
      rows.push([h(relationNames[relation.kind]||t('商城推荐','Store recommendation'))+' · '+(target?productLink(target,target.name):h(relation.sku)),evidenceLink(relation.source||p.url)]);
    }
    const audit=p.documentAudit;
    const checked=audit?`<p class="caption">${h(t('关联 '+audit.linked+' 份来源，已筛查可读正文 '+audit.checked+' 份，其中 '+audit.parsed+' 份含目标内容。已确认适用于此 SKU 的资料记录 '+(audit.verifiedRows||0)+' 条。未查全 '+audit.unread+' 份，读取失败 '+audit.failed+' 份。',audit.linked+' linked sources. Readable content was screened in '+audit.checked+', and '+audit.parsed+' contained relevant sections. '+(audit.verifiedRows||0)+' source records were verified for this SKU. '+audit.unread+' sources remain incomplete and '+audit.failed+' failed.'))}</p>`:'';
    const sources=(p.documentChecks||[]).map(c=>{
      const status=h(documentState(c.status))+(c.reason?`<small>${h(sourceReason(c.reason))}</small>`:'');
      const checked=c.pages?.length?c.pages.map(page=>link(c.url.split('#')[0]+'#page='+page,t('文件第 '+page+' 页 ↗','File page '+page+' ↗'))).join(' · '):link(c.url,t('打开 ↗','Open ↗'));
      const worksheets=(c.worksheets||[]).map(w=>'<small>'+h(w.name+' · '+t('第 '+w.firstRow+'–'+w.lastRow+' 行','Rows '+w.firstRow+'–'+w.lastRow))+'</small>').join('');
      const sections=(c.sectionLinks||[]).map(item=>{
        const label=item.page?t('第 '+item.page+' 页','Page '+item.page):item.heading||t('原文段落','Original section');
        const scopes={example:t('示例配置','Example configuration'),example_configuration:t('示例配置','Example configuration'),component_guide:t('部件自身资料','Component documentation'),assembly_components:t('装机组成','Installed components'),certification:t('认证送审材料','Certification submission materials'),ecosystem:t('生态系统通用资料','Ecosystem reference')};
        const scope=scopes[item.kind]||t('清单适用型号待核','List with unconfirmed model scope');
        return link(item.url,scope+' · '+label+' ↗');
      }).filter(Boolean);
      const pending=sections.length?`<small>${sections.join(' · ')}</small>`:'';
      return [h(c.title||c.url),status,checked+worksheets+pending];
    });
    const supplemental=referenceSections(p,['certification_info','certification_info_eccn','faq_list']);
    return (window.InternalUI?.product(p,lang,'all')||'')+checked+documentConflicts(p)+table([t('文档或来源','Document or source'),t('打开','Open')],rows)+productReview(p)+(sources.length?`<details class="summary"><summary>${t('查看各来源的核对结果','Review status for each source')}</summary>${table([t('资料','Source'),t('本轮检查','Review status'),t('原文','Original')],sources)}</details>`:'')+(supplemental?`<details class="summary"><summary>${t('官网其他详情栏目','Additional store sections')}</summary>${supplemental}</details>`:'');
  }
  function documentConflicts(p,packingOnly=false){
    const entries=(p.documentConflicts||[]).filter(c=>!packingOnly||c.field!=='fieldOfView');
    const rows=entries.map(c=>[h(c.publishedSku),h(c.name)+'<small>'+evidenceLink(c.source)+'</small>',h(c.catalogName)+'<small>'+evidenceLink(c.catalogUrl)+'</small>']);
    const label=packingOnly?t('商城装箱与其他官方资料有差异，报价前需核实','Packing list differs from other official guidance; verify before quoting'):t('手册与商城资料有差异，选型前需核实','Manual and store details disagree; verify before selection');
    return rows.length?`<details class="summary"><summary>${label} · ${num(rows.length)}</summary>${table(['SKU',t('手册写法','Manual description'),t('商城写法','Store description')],rows)}</details>`:'';
  }
  function documentState(value){
    return ({parsed:t('已筛查，有目标内容','Screened, relevant sections found'),empty:t('已筛查，未检出目标内容','Screened, no relevant sections found'),unread:t('未查全','Unchecked or incomplete'),failed:t('读取失败','Failed')})[value]||value||'';
  }
  function sourceReason(value){
    const scope={otherResourceType:t('其他文件类型或网站入口','Other resource types or site landing pages'),otherPublisher:t('第三方发布者','Third-party publisher'),publisherTerms:t('发布方限制自动采集','Publisher restricts automated collection'),robotsDisallow:t('站点规则禁止采集','Disallowed by site rules'),unverifiedSiteRules:t('未能核对站点抓取规则','Site collection rules could not be verified'),unverifiedPublicRepository:t('未能确认该仓库公开','Repository could not be verified as public'),ocr_partial:t('仅部分扫描页完成文字筛查','Scanned pages only partially screened'),document_model_conflict:t('附件与商品的型号或配置有冲突','Attachment and product model or configuration disagree')};
    if(scope[value])return scope[value];
    if(value==='publisher_terms')return t('发布者条款限制自动采集','Publisher terms restrict automated collection');
    if(value==='section_needs_review')return t('识别到目标栏目，其行或适用范围仍待核对','Target section found; rows or scope need review');
    if(value==='protected_pdf')return t('受保护的 PDF','Protected PDF');
    if(value==='ocr_candidate_needs_review')return t('扫描内容已识别，待人工复核','Scanned text recognized, awaiting review');
    if(/^unreadable_|^pdf_text_/.test(value))return t('文档解析失败','Document parser failed');
    const labels={excluded_robots:t('站点抓取规则限制','Excluded by crawler rules'),robots_unverified:t('暂时无法核对站点抓取规则','Crawler rules temporarily unavailable'),external_not_checked:t('第三方资源','External resource'),other_resource_type:t('非 Wiki 或 PDF','Other resource type'),host_cooldown:t('官网限流冷却','Source rate limit'),github_rate_limit:t('GitHub 速率限制','GitHub rate limit'),redirect_other_host:t('跳转到其他主机','Redirects to another host'),limit_bytes:t('超出单份文档大小限制','File exceeds processing size limit'),not_yet_checked:t('等待核对','Awaiting review'),network:t('网络读取失败','Network error'),encrypted_pdf:t('加密 PDF','Encrypted PDF'),no_text_layer:t('缺少可读取的文字层','No readable text layer'),long_pdf:t('超过单份文件页数限制','Exceeds page processing limit'),no_wiki_article:t('未找到对应 Wiki 正文','Wiki article not found'),not_pdf:t('链接返回的不是 PDF','Linked response is not a PDF'),pdf_text_KeyError:t('PDF 文本层解析失败','Failed to parse PDF text'),unreadable_LimitReachedError:t('PDF 读取超出解析限制','PDF parser limit reached')};
    return labels[value]||(/^http_\d+$/.test(value)?value.replace('http_','HTTP '):value);
  }
  function sectionNames(){
    return {product_feature_description:t('特性','Features'),specification:t('技术规格','Specifications'),hardware_overview:t('硬件概览','Hardware overview'),product_application_description:t('应用','Applications'),documents:t('文档','Documents'),certification_info:t('认证栏目','Certification section'),certification_info_tech:t('技术参数附表','Technical details'),certification_info_part:'Part List',certification_info_eccn:t('ECCN 等编码','ECCN and other codes'),faq_list:'FAQ'};
  }
  function pageException(p){
    const audit=p.detailAudit||{},error=audit.error||'';
    if(audit.identity?.reason==='different_displayed_sku')return t('网页实际展示其他 SKU','Page displays a different SKU');
    if(audit.identity?.reason==='different_product_id')return t('网页展示不同的商品 ID','Page displays a different product ID');
    if(error==='DETAIL_SKU_NOT_VERIFIED')return t('网页未能确认该 SKU，未采用页面详情','Page did not confirm this SKU; page details were omitted');
    if(/^STORE_HTTP_\d+$/.test(error))return 'HTTP '+error.slice(11);
    if(error==='ROBOTS_EXCLUDED'||audit.state==='excluded')return t('官网抓取规则或可用地址限制','Collection rules or available URL prevent access');
    if(error==='ROBOTS_UNVERIFIED')return t('未能核实官网抓取规则','Store crawler rules could not be verified');
    return error||t('商品页未能读取','Product page could not be read');
  }
  function landingEvidence(p){
    const info=p.detailAudit?.identity;
    if(!info)return '';
    const shown=(info.displayedSkus||[]).map(sku=>{
      const item=search.bySku.get(String(sku).toLowerCase());
      return item?productLink(item):h(sku);
    });
    const fields=[];
    if(shown.length)fields.push(t('页面 SKU','Displayed SKU')+' '+shown.join(', '));
    if(info.displayedStoreIds?.length)fields.push(t('页面商品 ID','Displayed product ID')+' '+h(info.displayedStoreIds.join(', ')));
    if(info.resolvedUrl)fields.push(link(info.resolvedUrl,t('查看跳转后的官网页面 ↗','Open final store page ↗')));
    return fields.join(' · ');
  }
  function productReview(p){
    const a=p.detailAudit;
    if(!a)return '';
    const labels=sectionNames(),status={empty:t('已查为空','Checked empty'),present:t('已查有内容','Checked, content present'),unread:t('尚未核对','Unchecked'),excluded:t('官网规则或链接限制','Excluded by rules or URL'),source_error:t('读取失败','Read failed')};
    const explain={source_error:t('商品页读取失败或未能验证此 SKU。','The page could not be read or its SKU could not be confirmed.'),excluded:t('此次页面检查受官网抓取规则或可用 URL 限制。','The store policy or the available URL precluded a page check.'),unread:t('本轮尚未完成此商品页核对。','The full page has not been checked in this review.'),nonempty:t('本轮已核对十个独立栏目，至少一项有内容。','All ten dedicated sections were checked; at least one has content.'),empty:t('本轮已核对十个独立栏目，各栏均未列内容。','All ten dedicated sections were checked and were empty.')};
    const data=[[t('商品目录正文','Catalogue product description'),h(status[a.body]||status.unread)]];
    for(const [code,state] of Object.entries(a.fields||{}))data.push([h(labels[code]||code),h(status[state]||state)]);
    const exception=['source_error','excluded'].includes(a.state)?`<p class="caption">${h(pageException(p))} ${landingEvidence(p)}</p>`:'';
    return `<details class="summary"><summary>${t('本轮商品资料核对','Review of this product')}</summary><p class="caption">${h(explain[a.state]||'')} ${h((a.checkedAt||a.bodyCheckedAt||'').slice(0,10))}</p>${exception}${table([t('来源栏目','Source section'),t('状态','Status')],data)}</details>`;
  }
  function renderAssistant(){
    const result=search.lookup(state.query,{ranked:false}),p=state.pin?search.bySku.get(state.pin.toLowerCase()):result.primary;
    currentProduct=p;currentAlternatives=p?search.alternatives(p,state.query,result.needs):[];
    view.innerHTML=title(t('选型查询','Product finder'),t('从客户指定的产品开始，也可以按应用需求查找。','Start with a named product or search by application requirements.'))+queryForm()+
      (p?`<div class="results"><div class="primary-stack">${mainCard(p,result)}${facts(p)}</div><div class="right-stack">${related(p,currentAlternatives)}</div></div>${information(p)}`:`<div class="empty">${t('没有匹配的产品。可尝试型号、SKU 或具体接口需求。','No matching product. Try a model, SKU or interface requirement.')}</div>`);
  }
  function renderCatalog(){
    let items=db.products.filter(p=>state.group==='*'||(state.group==='menu'?p.groups.length:state.group==='outside'?!p.groups.length:p.groups.includes(state.group)));
    for(const p of items)if(!directoryText.has(p.sku))directoryText.set(p.sku,normalizeCatalogText([p.name,p.sku,p.summary,...(p.internal?.names||[]),...p.groups,...p.paths.flat()].join(' ')));
    const term=state.catalogQuery.trim();
    if(term){
      const matches=catalogQueryMatcher(term);
      items=items.filter(p=>matches(directoryText.get(p.sku)));
    }
    const pages=Math.max(1,Math.ceil(items.length/25));state.page=Math.min(state.page,pages);
    const pageItems=items.slice((state.page-1)*25,state.page*25);
    catalogPage={skus:pageItems.slice(0,12).map(p=>p.sku),total:items.length};
    view.innerHTML=title(t('产品目录','Product catalogue'),t('按品类浏览，或用产品名、常用中英文词和 SKU 定位。','Browse categories or search by name, common Chinese and English terms, or SKU.'))+
      `<div class="panel directory"><div class="catalog-controls"><input id="cattext" aria-label="${t('搜索产品目录','Search catalogue')}" placeholder="${t('产品名称或 SKU','Product name or SKU')}" value="${h(state.catalogQuery)}"><select id="category" aria-label="${t('筛选分类','Filter category')}">${[['*',t('全部商品','All products')],['menu',t('Products 菜单内','In Products menu')],['outside',t('菜单外或本地商品','Outside menu / local')],...db.categories.map(c=>[c.name,c.name])].map(([k,v])=>`<option value="${h(k)}" ${state.group===k?'selected':''}>${h(v)}</option>`).join('')}</select></div><div class="catalog-count">${num(items.length)} ${t('个商品','products')}</div>`+
      table([t('产品','Product'),'SKU',t('商城公开价','Store price'),t('商品页','Store page')],pageItems.map(p=>['<div class="catalog-name">'+photo(p)+productLink(p,p.name,'')+'</div>',productLink(p),h(price(p)),link(p.url,t('打开 ↗','Open ↗'))]))+
      `<div class="pager"><button data-page="-1" ${state.page===1?'disabled':''}>${t('上一页','Previous')}</button><span>${state.page} / ${pages}</span><button data-page="1" ${state.page===pages?'disabled':''}>${t('下一页','Next')}</button></div></div>`;
    syncChat();
  }
  function chatContext(){
    const view=state.view;
    if(view==='assistant'){
      const p=currentProduct;
      if(!p)return {view,query:state.query};
      const tab=state.tab||defaultTab(p);
      const visibleSkus=tab==='accessories'?matchingOptions(p).filter(g=>!offerOnly(g)||offersExpanded(p.sku)).map(g=>g.match?.product?.sku).filter(Boolean).slice(0,12):[];
      return {view,sku:p.sku,tab,query:state.query,filter:tab==='accessories'?state.accFilter:'',visibleSkus,alternativeSkus:currentAlternatives.map(r=>r.p.sku)};
    }
    if(view==='catalog')return {view,query:state.catalogQuery,category:state.group,page:state.page,total:catalogPage.total,visibleSkus:catalogPage.skus};
    if(view==='coverage')return {view};
    return window.Workbench?.chatContext(view)||{view};
  }
  function chatContextLabel(c=chatContext()){
    let label='';
    if(c.view==='assistant'){
      const p=c.sku&&search.bySku.get(c.sku.toLowerCase());
      if(!p)return [t('选型查询','Product finder'),c.query].filter(Boolean).join(' · ');
      label=[short(p),'SKU '+p.sku,tabs(p)[c.tab],c.filter].filter(Boolean).join(' · ');
    }else if(c.view==='catalog'){
      const group={'*':t('全部商品','All products'),menu:t('Products 菜单内','In Products menu'),outside:t('菜单外或本地商品','Outside menu / local')}[c.category]||c.category;
      label=[t('产品目录','Catalogue'),group,c.query,t(c.total+' 个商品',c.total+' products'),t('第 '+c.page+' 页','Page '+c.page)].filter(Boolean).join(' · ');
    }else if(c.view==='favorites'){
      label=t('我的收藏','Favorites')+' · '+(c.selectedSkus?.length?t('已选 '+c.selectedSkus.length+' 项',c.selectedSkus.length+' selected'):t(c.total+' 个收藏',c.total+' saved'));
    }else if(c.view==='custom'){
      label=[t('定制服务','Customization'),c.projectDraft?.title||'',c.sku,c.query,c.selectedSkus?.length?t(c.selectedSkus.length+' 个关联 SKU',c.selectedSkus.length+' linked SKUs'):''].filter(Boolean).join(' · ');
    }else if(c.view==='developer')label=t('开发者设置','Developer settings')+' · '+({settings:t('语言与 AI','Language & AI'),products:t('产品编辑','Product editor'),updates:t('目录更新','Catalogue updates')}[c.tab]||'');
    else label=t('采集概况','Catalogue coverage');
    return label;
  }
  function openChatEvidence(){
    if(state.view==='assistant'&&currentProduct){
      const current=state.tab||defaultTab(currentProduct);
      document.querySelector(`.tabs [data-tab="${current}"]`)?.click();
      document.querySelector('.information')?.scrollIntoView({block:'start'});
    }else if(state.view==='developer')window.Workbench?.openSettings();
    else view.scrollIntoView({block:'start'});
  }
  function syncChat(){window.WorkbenchChat?.sync();}
  function collectionReport(){
    const audit=base.audit;
    if(!audit)return '';
    const directory=audit.directory,detail=audit.detail,sm=audit.sitemap;
    const heading=t('最近一次全站核对','Latest full-catalogue review');
    const sourceNames={listing:t('公开商品接口','Public product endpoint'),sitemap:t('站点地图','Sitemap'),robots:t('抓取规则','Crawler rules')};
    const sourceLinks=Object.entries(sourceNames).map(([key,name])=>link(audit.sources?.[key],name+' ↗')).filter(Boolean).join(' · ');
    const menuStates={nonempty:0,empty:0,source_error:0,excluded:0,unread:0};
    for(const p of base.products)if(p.groups?.length)menuStates[p.detailAudit?.state||'unread']++;
    const rows=[
      [t('海外公开搜索返回的不同 SKU','Distinct SKUs in public product search'),directory.publicSearchSkuCount],
      [t('由其他官网入口确认的 SKU','SKUs confirmed through additional store routes'),directory.liveSkuCount-directory.publicSearchSkuCount],
      [t('地图留档且普通商品页返回 HTTP 404','Sitemap records whose product pages returned HTTP 404'),base.products.filter(p=>p.catalogStatus==='live_secondary'&&p.storePageStatus==='not_found').length],
      [t('可检索 SKU 中有正数起价 / 地图留档有历史价格','Searchable SKUs with a positive starting price / priced sitemap records'),num(base.products.filter(p=>p.catalogStatus==='live'&&p.price>0).length)+' / '+num(base.products.filter(p=>p.catalogStatus==='live_secondary'&&p.price>0).length)],
      [t('仅通过菜单发现的 SKU','Menu-only SKUs'),directory.menuOnly?.length],
      [t('本次新增 / 旧记录本次未返回','New / retained from previous catalogue'),num(directory.addedSkuCount)+' / '+num(directory.retainedPrevious)],
      [t('站点地图链接 / 含商品 ID 的不同链接','Sitemap URLs / URLs containing a product ID'),num(sm.urls)+' / '+num(sm.productUrls)],
      [t('地图中不同商品 ID / 尚无相同目录 URL ID','Distinct product IDs in sitemap / IDs absent from catalogue URLs'),num(sm.productIds)+' / '+num(sm.unmatchedProductIdCount)],
      [t('正文已读且有内容 / 官网正文为空','Descriptions checked with text or media / checked empty'),num(directory.body?.present)+' / '+num(directory.body?.empty)],
      [t('完整详情十个栏目均已核对','SKUs with all ten dedicated sections checked'),detail.checked],
      [t('十个栏目中有内容 / 全部为空','At least one nonempty section / all ten empty'),num(detail.nonempty)+' / '+num(detail.empty)],
      [t('官网抓取规则或网址限制 / 读取失败 / 尚未查全','Excluded by rules or URL / failed / not fully checked'),[detail.excluded,detail.source_error,detail.unread].map(num).join(' / ')],
      [t('Products 菜单内的不重复 SKU：详情有内容 / 为空 / 失败 / 排除 / 待查','Unique SKUs in the Products menu: nonempty details / empty / failed / excluded / unchecked'),Object.values(menuStates).map(num).join(' / ')]
    ];
    if(audit.images){
      const im=audit.images;
      rows.push([t('可用主图 SKU / 不同 JPG 文件','SKUs with a verified local photo / distinct JPEGs'),num(im.verifiedSkus)+' / '+num(im.verifiedFiles)],
        [t('官网未提供有效主图 / 有图源但未能取得','Missing valid store photo / source unavailable'),num(im.missingSourceSkus)+' / '+num(im.failedSkus)]);
    }
    const d=audit.documents;
    let documentReport='';
    if(d){
      const kinds={wiki:'Wiki',pdf:'PDF',spreadsheet:t('清单工作表','List spreadsheets'),catalogue:t('官方年度目录','Official annual catalogue'),reference:t('其他链接资源','Other linked resources')};
      documentReport=`<h3>${t('Wiki、PDF 与其他链接','Wiki, PDFs and linked resources')}</h3><p class="caption">${h(t('共发现 '+num(d.uniqueLinked)+' 个不同地址，已筛查 '+num(d.uniqueChecked)+' 个来源的可读正文。仅对可确认归属的型号使用文档条目。',num(d.uniqueLinked)+' distinct URLs were identified. Readable content was screened in '+num(d.uniqueChecked)+' sources. Findings are assigned only where their model scope can be verified.'))}</p>`+
        table([t('来源类型','Source type'),t('已筛查有目标内容','Screened, target sections found'),t('已筛查无目标内容','Screened, no target sections'),t('未查全','Incomplete'),t('读取失败','Failed')],Object.entries(d.byKind||{}).map(([key,v])=>[h(kinds[key]||key),num(v.parsed),num(v.empty),num(v.unread),num(v.failed)]));
      const allowed=d.officialScopeSummary;
      if(allowed){
        const excluded=Object.entries(allowed.excludedByReason||{});
        documentReport+=`<h3>${t('可自动核对的官方资料','Official sources eligible for automated review')}</h3><p class="caption">${t('按不同来源网址统计。发布方、文件类型与公开访问规则决定是否纳入；单份文件返回错误或无法读完时，保留在应核范围内。','Counts use distinct source URLs. Publisher, resource type and public access rules define the scope. Individual file errors and incomplete reads remain in scope.')}</p>`+
          table([t('核对范围与结果','Scope and outcome'),t('来源数','Sources')],[
            [t('全部关联网址','All linked URLs'),num(allowed.linked)],[t('仅保留链接，范围外或发布方有限制','Link only: outside scope or restricted by the publisher'),num(excluded.reduce((n,[,count])=>n+count,0))],
            [t('应核的官方资料','Eligible official resources'),num(allowed.eligible)],[t('其中已完成目标内容筛查','Completed target-content screening'),num(allowed.completed)],
            [t('其中已尝试、未能完成','Attempted and incomplete'),num(allowed.attemptedIncomplete)],[t('其中尚未尝试','Not attempted'),num(allowed.notAttempted)],
            [t('其中旧记录未确认是否已对该地址发起请求','Earlier records without confirmed per-URL attempts'),num(allowed.attemptUncertain)]
          ]);
        if(excluded.length)documentReport+=`<details class="summary"><summary>${t('查看仅保留链接的原因','View reasons for link-only coverage')}</summary>${table([t('原因','Reason'),t('来源数','Sources')],excluded.map(([reason,n])=>[h(sourceReason(reason)),num(n)]))}</details>`;
        const pending=Object.entries(allowed.byOutcomeAndReason?.attemptedIncomplete||{}).sort((a,b)=>b[1]-a[1]);
        if(pending.length)documentReport+=`<details class="summary"><summary>${t('查看已尝试但未读完的原因','View reasons for incomplete attempts')}</summary>${table([t('原因','Reason'),t('来源数','Sources')],pending.map(([reason,n])=>[h(sourceReason(reason)),num(n)]))}</details>`;
        if(allowed.originalReadUnion!==undefined)documentReport+=`<p class="caption">${h(t('取得线上原件 '+num(allowed.onlineBodyRetrieved)+' 个，读取已固定版本的官方 Wiki 正文 '+num(allowed.offlineOriginalRead)+' 个。合计 '+num(allowed.originalReadUnion)+' 个不同地址至少取得一种原文。','Online originals were retrieved for '+num(allowed.onlineBodyRetrieved)+' URLs, and '+num(allowed.offlineOriginalRead)+' Wiki originals were read from the pinned official revision. Together these cover '+num(allowed.originalReadUnion)+' unique URLs.'))}</p>`;
      }
      documentReport+=`<p class="caption">${h(t(num(d.verifiedSkus)+' 个 SKU 有 '+num(d.verifiedRows)+' 条可确认归属的来源记录，包含不同资料对同一物料的交叉核对。',num(d.verifiedRows)+' scoped source records across '+num(d.verifiedSkus)+' SKUs include independent confirmations of the same item.'))}</p>`;
      if(d.sourcesWithSkuFacts!==undefined)documentReport+=table([t('文档证据口径','Document evidence measure'),t('数量','Count')],[
        [t('可为明确 SKU 提供事实的不同来源','Distinct sources with SKU-specific or verified family facts'),num(d.sourcesWithSkuFacts)],
        [t('不重复的主 SKU 与配件 SKU 组合','Distinct host SKU and accessory SKU pairs'),num(d.distinctAccessorySkuPairs)],
        [t('有文档装箱明细的主 SKU','Host SKUs with documented package contents'),num(d.skusWithDocumentPackingRows)],
        ...(d.wikiSeriesServiceSkus!==undefined?[[t('已获 Wiki 具体定制服务依据的 SKU / 系列指南','SKUs with specific Wiki customization evidence / family guides'),num(d.wikiSeriesServiceSkus)+' / '+num(d.targetedWikiServiceGuides)]]:[])
      ]);
      if(d.pdfTextPages!==undefined){
        const fingerprinted=d.pdfTextPagesWithoutDigest!==undefined;
        const pages=fingerprinted?t('按文件指纹去重后的 PDF 文字层筛查覆盖 '+num(d.pdfTextPages)+' 页。另有 '+num(d.pdfTextFilesWithoutDigest)+' 个早期来源，共 '+num(d.pdfTextPagesWithoutDigest)+' 页次，已筛查但无法跨链接去重。','Text screening covered '+num(d.pdfTextPages)+' pages after file-hash deduplication. A further '+num(d.pdfTextPagesWithoutDigest)+' page reads across '+num(d.pdfTextFilesWithoutDigest)+' earlier sources lack hashes for cross-link deduplication.'):t('本阶段记录 PDF 文字层筛查 '+num(d.pdfTextPages)+' 页次，文件别名可能重复。','This stage recorded '+num(d.pdfTextPages)+' PDF page reads, which may include files linked under several URLs.');
        documentReport+=`<p class="caption">${h(pages+' '+t('扫描页经 OCR 识别到文字 '+num(d.pdfOcrPagesWithText)+' 页。','OCR found text on '+num(d.pdfOcrPagesWithText)+' scanned pages.'))}</p>`;
      }
      const reasons=Object.entries(d.unreadAndFailureReasons||{}).sort((a,b)=>b[1]-a[1]);
      if(reasons.length)documentReport+=`<details class="summary"><summary>${t('范围限制与异常原因','Scope limits and source exceptions')}</summary>${table([t('原因','Reason'),t('不同来源数','Distinct sources')],reasons.map(([k,v])=>[h(sourceReason(k)),num(v)]))}</details>`;
      if(d.publishedUnmatchedSkus?.length){
        const printed=d.publishedUnmatchedSkus.map(item=>[h(item.sku),(item.pageUrls||[item.source]).map((url,index)=>link(url,t('文件第 '+item.pages[index]+' 页 ↗','File page '+item.pages[index]+' ↗'))).join(' · ')]);
        const lookup=audit.supplementarySkuLookup;
        const scope=lookup?.requested?.length?`<p class="caption">${h((lookup.checkedAt||'').slice(0,10))} · ${h(t('官网对 '+lookup.requested.length+' 个货号的精确筛选返回 '+lookup.totalCount+' 个商品。','An exact store search for '+lookup.requested.length+' SKUs returned '+lookup.totalCount+' products.'))} ${link(lookup.source,t('查询来源 ↗','Search source ↗'))}</p>`:'';
        documentReport+=`<details class="summary"><summary>${t('年度目录列出、尚未匹配商城商品的 SKU','Annual catalogue SKUs without a verified store record')} · ${num(printed.length)}</summary>${scope}${table(['SKU',t('年刊原文','Annual catalogue')],printed)}</details>`;
      }
      const repo=audit.wikiRepository;
      if(repo)documentReport+=`<p class="caption">${h(t('另核对 '+num(repo.read)+' 份官方英文 Wiki 源文件。'+num(repo.purchasePages??repo.pages)+' 页的购买链接与 '+num(repo.purchaseSkus??repo.matchedSkus)+' 个目录 SKU 核对一致。',num(repo.read)+' English Wiki source files were checked. Purchase links on '+num(repo.purchasePages??repo.pages)+' Wiki pages matched '+num(repo.purchaseSkus??repo.matchedSkus)+' store SKUs.'))} ${repo.verifiedDeclaredPages?h(t('其中另核对了 '+num(repo.verifiedDeclaredPages)+' 页明确声明的 SKU 及型号，共 '+num(repo.verifiedDeclaredSkus)+' 个不同 SKU。','Explicit SKU metadata and titles on '+num(repo.verifiedDeclaredPages)+' pages matched '+num(repo.verifiedDeclaredSkus)+' distinct SKUs.')):''} ${link(repo.repository+'/tree/'+repo.revision,t('官方 Wiki 版本 ↗','Official Wiki revision ↗'))}</p>`;
    }
    const labels=sectionNames();
    const perField=Object.entries(audit.fields||{}).map(([key,value])=>[h(labels[key]||key),num(value.present),num(value.empty),num(value.source_error),num(value.excluded),num(value.unread)]);
    const candidates=sm.priorUnmatchedProductCandidates||sm.legacyProductCandidates||[];
    const exceptionRows=candidates.map(item=>[h(item.id),link(item.url,t('地图地址 ↗','Sitemap URL ↗')),h(item.sku||''),h(routeStatus(item.redirectCode?'redirect':item.state))+(item.redirectCode?' '+h(item.redirectCode):'')]);
    const pageExceptions=base.products.filter(p=>['source_error','excluded'].includes(p.detailAudit?.state));
    const exceptionGroups=new Map();
    for(const p of pageExceptions){
      const reason=pageException(p);
      if(!exceptionGroups.has(reason))exceptionGroups.set(reason,[]);
      exceptionGroups.get(reason).push(p);
    }
    const pageReport=Array.from(exceptionGroups,([reason,products])=>`<details class="summary"><summary>${h(reason)} · ${num(products.length)} SKU</summary>${table(['SKU',t('产品','Product'),t('官网','Store')],products.map(p=>[productLink(p),h(p.name),link(p.url,t('查看来源 ↗','View source ↗'))]))}</details>`).join('');
    return `<section class="panel padded"><h2>${h(heading)}</h2><p class="caption">${h((audit.checkedAt||'').slice(0,10))} · ${sourceLinks}</p>`+
      table([t('核对项目','Review item'),t('数量','Count')],rows.filter(([,v])=>v!==undefined).map(([key,value])=>[h(key),typeof value==='number'?num(value):h(value)]))+
      (pageExceptions.length?`<details class="summary"><summary>${t('查看读取失败或受限的商品页','View failed or excluded product pages')} · ${num(pageExceptions.length)} SKU</summary>${pageReport}</details>`:'')+
      `<details class="summary"><summary>${t('按商品详情栏目查看','View checks by product-page section')}</summary>${table([t('官网栏目','Store section'),t('有内容','Nonempty'),t('已查为空','Checked empty'),t('读取失败','Failed'),t('规则排除','Excluded'),t('未检查','Unchecked')],perField)}</details>`+
      (candidates.length?`<details class="summary"><summary>${h(t('查看商品 ID 对账明细','View sitemap product ID reconciliation'))}</summary>${table([t('商品 ID','Product ID'),t('官网','Store'),'SKU',t('核对状态','Review status')],exceptionRows)}</details>`:'')+
      documentReport+'</section>';
  }
  function routeStatus(code){
    const labels={unread:t('尚未核对','Unchecked'),excluded:t('规则限制','Excluded by policy'),homepage:t('商城首页','Homepage'),redirect:t('重定向','Redirect'),product:t('官网商品','Store product'),resolved_product:t('已确认商品','Confirmed product'),resolved_nonproduct:t('已确认为其他类型页面','Confirmed non-product page'),no_route:t('官网查询无匹配','No match in public routing'),missing:t('无匹配路由','No matched route')};
    return labels[code]||code||'';
  }
  function renderCoverage(){
    const s=db.stats;
    const attributeCounts={present:0,empty:0,unparsed:0,unread:0};
    let reviewProducts=0,reviewRows=0;
    for(const p of base.products){
      const status=p.attributes?.length?'present':p.attributeStatus;
      attributeCounts[Object.hasOwn(attributeCounts,status)?status:'unread']++;
      if(p.unclassifiedRows?.length){reviewProducts++;reviewRows+=p.unclassifiedRows.length;}
    }
    const cards=[[s.total,t('公开目录 SKU','Store SKUs')],[s.menu,t('菜单内 SKU','SKUs in menu')],[db.categories.length,t('一级分类','Menu categories')],[s.images,t('有本地主图的 SKU','SKUs with a local image')]];
    view.innerHTML=title(t('采集概况','Catalogue coverage'),t('下列统计对应海外商城基础数据，本地新增与编辑另行保存。','These totals describe the official base catalogue. Local additions and edits are saved separately.'))+
      `<div class="metrics">${cards.map(([v,l])=>`<div class="panel"><strong>${num(v)}</strong><small>${h(l)}</small></div>`).join('')}</div>`+collectionReport()+`<div class="panel padded"><h2>${t('当前本地可查询的字段','Fields available in the local snapshot')}</h2>`+
      table([t('字段','Field'),t('SKU 数量','SKUs')],[
        [t('有商城商品或回退链接','Store product or fallback URL'),s.urls],[t('已收录正数起价（含地图留档）','Recorded positive starting price, including sitemap records'),s.prices],
        [t('Part List 原表含属性','Attributes in a Part List section'),attributeCounts.present],[t('已查 Part List 未列属性','Checked Part List contains no attributes'),attributeCounts.empty],
        [t('Part List 属性原文待核','Part List attribute format requires review'),attributeCounts.unparsed],[t('Part List 尚未核对','Part List not yet checked'),attributeCounts.unread],
        [t('另据官方标题或手册核实的型号配置','Model configurations verified from an official title or manual'),base.products.filter(p=>p.modelSpecs?.length).length],
        [t('已提取技术规格表或清单','Extracted specification tables or lists'),s.specProducts??base.products.filter(p=>specCount(p)).length],
        [t('已列出随箱物料','With in-box items'),s.parts],[t('已确认扩展接口或配件','Verified accessories or expansion interfaces'),base.products.filter(p=>p.accessories?.some(a=>!storeOffer(a))).length],
        [t('商品页列有商城加购推荐','Products with store add-on offers'),base.products.filter(p=>p.accessories?.some(storeOffer)).length],
        [t('商品页的文档链接','Resources from store pages'),s.documents],[t('存有本轮或以往的商品页详情','Product-page details saved across all reviews'),s.sections],
        [t('官方 Wiki 资料或已核事实','Official Wiki links or findings'),s.wikiLinked],[t('使用已核对的 Wiki 推荐依据','Curated Wiki selection findings'),s.wikiFacts],
        [t('有明确归属的文档条目','Verified, scoped document entries'),base.products.filter(p=>p.verifiedDocumentRows?.length).length]
      ].map(([l,v])=>[h(l),num(v)]))+
      (reviewRows?`<p class="caption">${h(t(num(reviewProducts)+' 个 SKU 有 '+num(reviewRows)+' 行官网原文待归类，可在这些产品的「原表待核」查看。',num(reviewRows)+' source rows across '+num(reviewProducts)+' SKUs await classification. Open “Rows to review” on those products.'))}</p>`:'')+
      `</div><div class="panel padded"><h2>${t('Products 分类','Products categories')}</h2><p class="caption">${t('同一个 SKU 可能出现在多个分类。','A SKU may appear in multiple categories.')}</p>`+
      table([t('分类','Category'),'SKU',t('本轮已读 / 可检查','Checked this review / eligible'),t('失败 / 排除 / 未查','Failed / excluded / unchecked'),t('历次有详情','Saved details'),t('有官网属性','Store attributes'),t('有箱内清单','Packing list'),t('官网','Store')],db.categories.map(c=>{
        const v=c.thisRunPages;
        return [`<button class="textbtn" data-group="${h(c.name)}">${h(c.name)}</button>`,num(c.count),v?num(v.checked)+' / '+num(v.eligible):'',v?[v.source_error,v.excluded,v.unread].map(num).join(' / '):'',num(c.sections),num(c.attributes),num(c.parts),link(c.url,t('打开 ↗','Open ↗'))];
      }))+'</div>';
  }
  function render(){
    if(state.view!=='assistant'){currentProduct=null;currentAlternatives=[];}
    shell();
    if(state.view==='assistant')renderAssistant();
    else if(state.view==='catalog')renderCatalog();
    else if(state.view==='coverage')renderCoverage();
    else if(connected&&window.Workbench)window.Workbench.render(state.view);
    else {
      const names={favorites:t('我的收藏','Favorites'),custom:t('定制服务','Customization'),developer:t('开发者','Developer')};
      view.innerHTML=title(names[state.view],t('请按上方说明启动完整工作台，再打开此页面。','Follow the instructions above to start the full workbench and open this page.'));
    }
    syncChat();
  }
  function historyControls(){
    const group=el('page-history');if(!group)return;
    group.hidden=!entry;group.setAttribute('aria-label',t('工作台浏览记录','Workbench history'));
    for(const button of group.querySelectorAll('[data-history]')){
      const back=Number(button.dataset.history)<0;
      const count=entry?Math.max(0,Math.min(historyWindow,back?entry.index-bounds.first:bounds.last-entry.index)):0;
      const label=back?t('上一页','Back'):t('下一页','Forward');
      button.disabled=!count;
      button.querySelector('.wb-history-label').textContent=label;
      button.setAttribute('aria-label',label);
      button.title=back?t('可后退 '+count+' 页（最多 5 页）','Back '+count+' of up to 5 pages'):t('可前进 '+count+' 页（最多 5 页）','Forward '+count+' of up to 5 pages');
    }
  }
  const uniqueEntry=()=>globalThis.crypto?.randomUUID?.()||Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
  function navHash(){
    if(state.view==='assistant'&&state.pin){
      const params=new URLSearchParams({product:state.pin});if(state.tab)params.set('tab',state.tab);
      return '#'+params;
    }
    return '#'+state.view;
  }
  function snapshot(){
    const offer=state.view==='assistant'&&document.querySelector('[data-nav-disclosure="offers"]');
    return {page:{...state},workspace:connected?window.Workbench.navigationState(state.view):null,offers:offer?offer.open:null};
  }
  function saveBounds(){
    try{sessionStorage.setItem(boundsKey,JSON.stringify(bounds));}catch{ /* The current tab still retains its history controls. */ }
  }
  function remember(){
    recentEntries.delete(entry.id);recentEntries.set(entry.id,entry);
    if(recentEntries.size>historyWindow*2+1)recentEntries.delete(recentEntries.keys().next().value);
    // Store the latest filter synchronously, including IME input immediately before a refresh.
    // Project prose, API keys and item edit forms are excluded by navigationState().
    try{sessionStorage.setItem(snapshotsKey,JSON.stringify([...recentEntries.values()]));}catch{}
  }
  function flushEntry(){
    clearTimeout(writeTimer);writeTimer=null;
    if(entry&&history.state?.seeedPage?.id===entry.id)history.replaceState({...history.state,seeedPage:entry},'');
  }
  function recordNavigation(mode){
    if(!entry||restoring)return;
    const next=snapshot();
    if(JSON.stringify(next)===JSON.stringify(entry.snapshot))return;
    if(mode==='push'){
      flushEntry();
      const index=entry.index+1;
      entry={chain:entry.chain,index,id:uniqueEntry(),snapshot:next};
      bounds={chain:entry.chain,first:Math.max(bounds.first,index-historyWindow),last:index};saveBounds();
      history.pushState({seeedPage:entry},'',navHash());historyControls();
      const workbenchLink=document.querySelector('#service-status .workbench-link');
      if(workbenchLink)workbenchLink.href=workspaceLink();
      const languageLink=document.querySelector('#service-status a[lang]');
      if(languageLink)languageLink.hash=location.hash;
    }else{
      entry={...entry,snapshot:next};
      clearTimeout(writeTimer);
      if(mode==='typing')writeTimer=setTimeout(flushEntry,350);else flushEntry();
    }
    remember();
  }
  function restoreEntry(target){
    clearTimeout(writeTimer);writeTimer=null;
    entry=recentEntries.get(target.id)||target;
    if(bounds?.chain!==entry.chain){
      let saved;try{saved=JSON.parse(sessionStorage.getItem(boundsKey));}catch{}
      bounds=saved?.chain===entry.chain?saved:{chain:entry.chain,first:entry.index,last:entry.index};
    }
    // The browser may travel farther back than the five pages offered by the workbench.
    bounds.first=Math.max(Math.min(bounds.first,entry.index),entry.index-historyWindow);
    bounds.last=Math.min(Math.max(bounds.last,entry.index),entry.index+historyWindow);saveBounds();
    restoring=true;
    try{
      const saved=entry.snapshot;Object.assign(state,saved.page);
      state.tab=canonicalTab(state.tab);
      if(state.pin&&!search.bySku.has(state.pin.toLowerCase()))state.pin='';
      if(connected)window.Workbench.restoreNavigation(state.view,saved.workspace);
      render();
      const offer=document.querySelector('[data-nav-disclosure="offers"]');
      if(offer&&typeof saved.offers==='boolean'&&offer.open!==saved.offers){offer.open=saved.offers;syncChat();}
    }finally{restoring=false;}
  }
  function queryState(q){
    state.query=q.trim();state.pin='';state.accFilter=/eu868/i.test(q)?'EU868':/us915/i.test(q)?'US915':'';
    if(/不随箱|不含|另购|not included|sold separately|not in the box/i.test(q))state.tab='accessories';
    else if(/随箱|装箱|箱内|in the box|pack(?:ing|age) (?:list|contents)/i.test(q))state.tab='parts';
    else if(/规格|属性|内存|存储|specifications?|attributes|\bstorage\b|\bram\b/i.test(q))state.tab='specs';
    else if(state.accFilter||/配件|扩展|选配|定制|wi[ -]?fi|无线网卡|accessor|optional|logo|customiz/i.test(q))state.tab='accessories';
    else state.tab='';
    state.view='assistant';
  }
  function runQuery(q){queryState(q);render();recordNavigation('push');window.scrollTo(0,0);}
  function resolveHash(fragment){
    const hash=fragment.replace(/^#/,'');
    if(hash.startsWith('product=')){
      const params=new URLSearchParams(hash);
      const sku=params.get('product'),tab=canonicalTab(params.get('tab')||'');
      const p=search.bySku.get(sku.toLowerCase());
      if(p)Object.assign(state,{view:'assistant',pin:p.sku,query:p.sku,accFilter:'',tab:Object.hasOwn(tabs(p),tab)?tab:''});
      else queryState(sku);
    }else if(views.has(hash))state.view=hash;
  }
  function navigateHash(hash){resolveHash(hash);render();recordNavigation('push');window.scrollTo(0,0);}
  function nativeRoute(){
    const target=history.state?.seeedPage;
    if(target&&views.has(target.snapshot?.page?.view)){
      if(target.id!==entry?.id)restoreEntry(target);
      return;
    }
    // A pasted or bookmarked fragment created by the browser already has a history slot.
    const index=entry?entry.index+1:0,chain=entry?.chain||uniqueEntry();
    resolveHash(location.hash);render();
    bounds={chain,first:Math.max(bounds?.first||0,index-historyWindow),last:index};saveBounds();
    entry={chain,index,id:uniqueEntry(),snapshot:snapshot()};remember();
    history.replaceState({...history.state,seeedPage:entry},'');historyControls();
  }
  document.addEventListener('submit',e=>{
    if(e.target.id==='ask'){e.preventDefault();runQuery(el('asktext').value);}
  });
  document.addEventListener('click',e=>{
    const anchor=e.target.closest('a[href^="#"]');
    if(anchor&&!e.defaultPrevented&&e.button===0&&!e.ctrlKey&&!e.metaKey&&!e.shiftKey&&!e.altKey){
      const hash=anchor.getAttribute('href');
      if(hash.startsWith('#product=')||views.has(hash.slice(1))){e.preventDefault();navigateHash(hash);return;}
    }
    const b=e.target.closest('button');if(!b)return;
    if(b.dataset.history){if(!b.disabled){flushEntry();history.go(Number(b.dataset.history));}return;}
    if(b.dataset.view){changeView(b.dataset.view);return;}
    if(b.dataset.example){runQuery(b.dataset.example);return;}
    if(b.dataset.tab){
      const jump=!b.closest('.tabs');state.tab=canonicalTab(b.dataset.tab);
      const old=document.querySelector('.information');
      if(old&&currentProduct){old.outerHTML=information(currentProduct);if(jump)document.querySelector('.information').scrollIntoView({block:'start',behavior:'smooth'});}
      recordNavigation('push');syncChat();
      return;
    }
    if(b.dataset.group){state.group=b.dataset.group;state.catalogQuery='';state.page=1;changeView('catalog');return;}
    if(b.dataset.page){state.page+=Number(b.dataset.page);renderCatalog();recordNavigation('push');window.scrollTo(0,0);}
  });
  document.addEventListener('change',e=>{if(e.target.id==='category'){state.group=e.target.value;state.page=1;renderCatalog();recordNavigation('push');}});
  document.addEventListener('toggle',e=>{if(e.target.isConnected&&e.target.matches?.('[data-nav-disclosure="offers"]'))recordNavigation('replace');},true);
  document.addEventListener('input',e=>{
    const id=e.target.id,pos=e.target.selectionStart,val=e.target.value;
    if(id==='accfilter'&&currentProduct){state.accFilter=val;el('tabbody').innerHTML=tabBody(currentProduct);syncChat();}
    else if(id==='cattext'){state.catalogQuery=val;state.page=1;renderCatalog();}
    else return;
    recordNavigation('typing');const field=el(id);field.focus();field.setSelectionRange(pos,pos);
  });
  async function start(){
    lang=new URLSearchParams(location.search).get('lang')==='en'?'en':'zh-CN';
    if(!publicPreview&&loopback&&window.Workbench&&window.WorkbenchChat){
      try{
        const data=await api('/api/state');
        if(typeof data.csrf==='string'&&data.csrf&&Array.isArray(data.favorites)&&Array.isArray(data.projects)){
          profile=data;lang=profile.language==='en'?'en':'zh-CN';connected=true;
        }
      }
      catch{connected=false;}
    }
    if(connected)window.InternalUI?.init({api,language:()=>lang,getState:()=>profile,getProduct:sku=>search?.bySku.get(String(sku).toLowerCase()),reloadData,openProduct});
    if(connected)window.Workbench.init({api,lang:()=>lang,getDb:()=>db,getState:()=>profile,getProduct:sku=>search?.bySku.get(String(sku).toLowerCase()),
      view,sidebar:el('sidebar-favorites'),openProduct,changeView,reloadData,onLanguage:snapLang,renderApp:render,onContextChange:syncChat,onNavigationChange:recordNavigation});
    rebuild();
    if(connected)window.WorkbenchChat.init({root:el('global-ai'),api,language:()=>lang,connected:()=>connected,profile:()=>({provider:profile.provider,providers:profile.providers}),
      getContext:chatContext,getContextLabel:chatContextLabel,openSettings:()=>window.Workbench?.openSettings(),
      openEvidence:openChatEvidence,openProject:id=>window.Workbench?.openProject(id),openProduct});
    window.addEventListener('popstate',nativeRoute);window.addEventListener('hashchange',nativeRoute);
    window.addEventListener('pagehide',flushEntry);nativeRoute();el('startup-help').hidden=true;
  }
  start().catch(()=>{view.textContent='目录未能打开，请按上方说明重新解压并刷新。 / The catalogue could not open. Extract the full ZIP and refresh.';});
})();
