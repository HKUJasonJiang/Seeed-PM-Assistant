(() => {
  'use strict';
  const view=document.getElementById('view');
  let base=window.SEEED_CATALOG;
  if(!base){view.textContent='产品目录未载入。The catalogue could not be loaded.';return;}
  let db=base, search, currentProduct, currentAlternatives=[];
  let profile={language:'zh-CN',provider:'deepseek',providers:{},favorites:[],projects:[],overrides:{}};
  let lang='zh-CN', connected=false;
  const state={view:'assistant',query:'J4012',pin:'',tab:'',accFilter:'',catalogQuery:'',group:'*',page:1};
  let catalogPage={skus:[],total:0};
  const t=(zh,en)=>lang==='en'?en:zh;
  const local=v=>localizedProductText(v,lang);
  const h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=n=>Number(n||0).toLocaleString(lang==='en'?'en-US':'zh-CN');
  const safe=u=>typeof u==='string'&&(/^https?:\/\//i.test(u)||/^(?:data\/jpg\/|\/user-images\/)[a-z\d._-]+$/i.test(u));
  const link=(url,label,cls='')=>safe(url)?`<a class="${cls}" href="${h(url)}" target="_blank" rel="noopener noreferrer">${h(label)}</a>`:'';
  const short=p=>p.name.match(/^reComputer\s+(?:(?:Industrial|Super|Robotics|Rugged)\s+)?[JR]\d+(?:-\d+)?(?:\s*\(w\/o power adapter\))?/i)?.[0]||p.name;
  const photo=(p,cls='')=>`<div class="photo ${cls}">${safe(p.image||p.imageUrl)?`<img loading="lazy" src="${h(p.image||p.imageUrl)}" alt="${h(p.name)}">`:''}</div>`;
  const productLink=(p,label=p.sku,cls='sku')=>`<a class="${cls}" href="#product=${encodeURIComponent(p.sku)}">${h(label)}</a>`;
  const title=(name,desc)=>`<div class="page-title"><h1>${h(name)}</h1><p>${h(desc)}</p></div>`;
  const table=(heads,rows)=>`<div class="table-scroll"><table><thead><tr>${heads.map(x=>`<th>${h(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${c||''}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const el=id=>document.getElementById(id);
  const price=p=>{
    const fmt=v=>new Intl.NumberFormat('en-US',{style:'currency',currency:p.currency||'USD'}).format(v);
    if(p.price>0)return (p.maxPrice>p.price?fmt(p.price)+' – '+fmt(p.maxPrice):fmt(p.price))+' '+(p.currency||'');
    return p.maxPrice>0?t('最高 '+fmt(p.maxPrice)+' · 起价待核','Up to '+fmt(p.maxPrice)+' · minimum unconfirmed'):'';
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
  function rebuild(){db=mergeProductData(base,profile.overrides);search=createSearch(db,lang,p=>window.Workbench?.isEligible(p)??Boolean(p.custom||p.customConfirmed));}
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
  const changeView=name=>{if(location.hash==='#'+name){state.view=name;render();}else location.hash=name;};
  const openProduct=sku=>{const target='#product='+encodeURIComponent(sku);if(location.hash===target)route();else location.hash=target;};
  function shell(){
    document.documentElement.lang=lang;document.title=t('Seeed Studio · 产品选型助手','Seeed Studio · Product workbench');
    document.querySelector('.app-name').textContent=t('产品选型助手','Product workbench');
    el('mode-name').textContent=connected?t('本地工作台','Local workspace'):t('离线目录','Offline catalogue');
    el('nav').setAttribute('aria-label',t('工作区','Workspace'));
    const entries=[['assistant','⌕',t('选型查询','Product finder')],['catalog','▦',t('产品目录','Catalogue')],['favorites','☆',t('我的收藏','Favorites')],['custom','▧',t('定制服务','Customization')],['coverage','▤',t('采集概况','Coverage')]];
    el('nav').innerHTML=entries.map(([id,icon,name])=>`<button data-view="${id}" aria-current="${id===state.view?'page':'false'}"><span aria-hidden="true">${icon}</span>${h(name)}</button>`).join('');
    el('developer-link').innerHTML='<span aria-hidden="true">⚙</span> '+t('开发者','Developer');
    el('developer-link').setAttribute('aria-current',state.view==='developer'?'page':'false');
    el('store-link').textContent=t('Seeed Studio 海外商城 ↗','Seeed Studio store ↗');
    el('service-status').innerHTML=connected?'':`<div class="service-note">${t('当前可以查询产品。双击项目内的「启动助手.cmd」即可使用收藏、编辑、更新和 AI。','Offline catalogue. Open “Start Assistant.cmd” in the project folder for saved work, updates and AI.')} <a href="http://127.0.0.1:8765/" rel="noopener">${t('打开已启动的工作台','Open a running workspace')} ↗</a></div>`;
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
    const proof=window.Workbench?.customizationInfo(p);
    const custom=proof?.text||(p.custom&&p.customUrl?local(p.custom):'');
    const customSource=proof?proof.url:p.customUrl;
    const attrs=p.attributes||[];
    const modelSpecs=p.modelSpecs||[];
    const fields=attrs.length?attrs:modelSpecs;
    const highlights=['RAM','Storage','Operating System','Network'].map(name=>fields.find(a=>a.name===name)).filter(Boolean).slice(0,3);
    return `<section class="panel selected"><div class="card-top"><div class="section-label"><i></i>${h(description)}</div>${connected&&window.Workbench?window.Workbench.productActions(p.sku):''}</div>
      ${p.url?`<div class="product-url">${link(p.url,p.url)}</div>`:''}
      <div class="hero-product">${photo(p,'hero-photo')}<div><div class="eyeline">${h(p.groups[0]||p.paths[0]?.[0]||(p.isLocal?t('本地产品','Local product'):t('海外商城','Global store')))}</div>
      <h2>${h(short(p))}</h2>${short(p)!==p.name?`<div class="official-name">${h(p.name)}</div>`:''}<div class="item-sku">SKU <b>${h(p.sku)}</b></div><div class="hero-price">${h(price(p))}</div>
      ${p.updated?`<span class="date">${t('商城快照','Store snapshot')} · ${h(p.updated)}</span>`:''}</div></div>
      ${terms.length?`<div class="tokens">${terms.map(s=>`<span>${h(s)}</span>`).join('')}</div>`:''}
      ${highlights.length?`<div class="spec-highlights">${highlights.map(a=>`<span><small>${h(attributeLabel(a.name))}</small> ${h(a.value)}</span>`).join('')}</div>`:''}
      ${missing.length?`<div class="missing-line"><b>${t('需另购 / 不随箱','Sold separately')}</b><span>${h(missing.join(lang==='en'?', ':'、'))}</span><button class="textbtn" data-tab="notes">${t('查看依据','Evidence')} ›</button></div>`:''}
      ${conflict?`<p class="warn"><b>${t('需求差异','Requirement gap')}</b> ${t('这个 Classic 版本不支持 Super 模式。请比较右侧的 Super J4012。','This Classic version does not support Super mode. Compare the Super J4012 in alternatives.')}</p>`:''}
      <div class="detail-key"><div><small>${t('定制范围','Customization')}</small><div>${h(custom)}</div>${customSource?link(customSource,t('查看来源 ↗','Source ↗')):''}</div>
      <div><small>${t('官网属性','Store attributes')}</small><button class="textbtn" data-tab="attributes">${attrs.length?t(attrs.length+' 项属性',attrs.length+' fields'):modelSpecs.length?t(modelSpecs.length+' 项型号配置',modelSpecs.length+' model specs'):recordLabel(p.attributeStatus)} ›</button></div>
      <div><small>${t('箱内清单','In the box')}</small><button class="textbtn" data-tab="parts">${p.parts.length?t(p.parts.length+' 项随附',p.parts.length+' included'):recordLabel(p.partStatus)} ›</button></div>
      <div><small>${t('配件与扩展','Accessories')}</small><button class="textbtn" data-tab="accessories">${p.accessories?.length?t(p.accessories.length+' 项配件',p.accessories.length+' items'):t('暂无已核条目','No verified items')} ›</button></div></div>
      ${p.sharedUrl?`<small>${t('多个 SKU 共用上述商品页。','Multiple SKUs share this product page.')}</small>`:''}
      ${p.summary?`<details class="summary"><summary>${p.isEdited?t('产品简介','Product summary'):t('官网产品简介','Store summary')}</summary><p>${h(p.summary)}</p></details>`:''}</section>`;
  }
  function facts(p){
    const e=p.wikiEvidence?.[0];
    if(e)return `<section class="panel evidence-panel"><div class="section-label">${t('选型依据','Selection evidence')}</div><p>${h(e[lang==='en'?'en':'zh'])}</p>${link(e.url,'Seeed Wiki · '+e.scope+' ↗','source-link')}</section>`;
    const none=p.isLocal?t('该 SKU 来自本地人工记录，尚无经核对的 Wiki 结论。','This SKU is a local record. It has no verified Wiki finding.'):t('尚无经核对的型号 Wiki 结论。可从商品页核对规格。','No model-specific Wiki finding has been verified. Check the product specifications on the store page.');
    return `<section class="panel evidence-panel"><div class="section-label">${t('选型依据','Selection evidence')}</div><p>${none}</p>${link(p.url,t('商品链接 ↗','Product link ↗'),'source-link')}${p.wikiLinks?.length?` <button class="textbtn" data-tab="docs">${t('查看随附 Wiki','Linked Wiki resources')} ›</button>`:''}</section>`;
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
  const defaultTab=p=>p.attributes?.length||p.modelSpecs?.length?'attributes':'parts';
  const tabs=p=>({attributes:t('官网属性','Store attributes'),parts:t('箱内清单','In the box'),accessories:t('配件与扩展','Accessories'),...(p.unclassifiedRows?.length?{raw:t('原表待核','Rows to review')}:{}),notes:t('定制与另购','Options & exclusions'),docs:t('文档与来源','Documents & sources')});
  function evidenceLink(url){
    if(!url)return '';
    if(/\/\/wiki\.seeedstudio\.com\//i.test(url))return link(url,t('系列 Wiki ↗','Family Wiki ↗'));
    if(/\.pdf(?:[?#]|$)/i.test(url)){
      const page=url.match(/#page=(\d+)/i)?.[1];
      return link(url,page?t('PDF 第 '+page+' 页 ↗','PDF page '+page+' ↗'):t('官方手册 ↗','Official manual ↗'));
    }
    return link(url,t('商品页 ↗','Store page ↗'));
  }
  function emptyRecord(p,isParts){
    const status=isParts?p.partStatus:p.attributeStatus;
    let explanation;
    if(p.isLocal)explanation=t('这是本地新增产品，暂无已核实的官网记录。','This local product has no verified store record.');
    else if(status==='empty')explanation=isParts
      ?t('已核对的商品栏目未列出随箱物料。官网属性和另购配件可在各自页签查看。','The checked store section lists no in-box items. See the separate tabs for attributes and accessories.')
      :t('已核对的官网栏目未列出可识别的产品属性。','The checked store section lists no product attributes.');
    else if(status==='unparsed')explanation=t('已读取官网栏目，原文格式仍需核对。','The store section was retrieved. Its contents still need review.');
    else explanation=isParts
      ?t('此 SKU 的随箱物料尚待核对。请查看商品页或官方手册。','The package contents for this SKU are pending verification. Check the product page or manual.')
      :t('此 SKU 的官网属性尚待核对。可在开发者页选择该 SKU 刷新。','Store attributes for this SKU are pending verification. Refresh the SKU in Developer.');
    return `<div class="record-empty"><p>${h(explanation)}</p>${p.unclassifiedRows?.length?`<button class="textbtn" data-tab="raw">${t('查看待核的官网原表行','View original rows awaiting review')} ›</button> · `:''}${evidenceLink((isParts?p.partSource:p.attributeSource)||p.url)}</div>`;
  }
  function information(p){
    const counts={attributes:p.attributes?.length||p.modelSpecs?.length,parts:p.parts.length,raw:p.unclassifiedRows?.length,accessories:p.accessories?.length,notes:p.notes.length+Number(Boolean(window.Workbench?.customizationInfo(p)||p.custom&&p.customUrl)),docs:new Set([...p.docs.map(d=>d.url),...(p.wikiLinks||[]).map(d=>d.url),...(p.wikiEvidence||[]).map(d=>d.url)]).size};
    const active=state.tab||defaultTab(p);
    return `<section class="panel information"><div class="tabs" role="tablist">${Object.entries(tabs(p)).map(([id,name])=>`<button role="tab" data-tab="${id}" aria-selected="${active===id}">${h(name)}${counts[id]?`<sup>${counts[id]}</sup>`:''}</button>`).join('')}</div><div id="tabbody" role="tabpanel">${tabBody(p)}</div></section>`;
  }
  function tabBody(p){
    const active=state.tab||defaultTab(p);
    if(active==='raw'){
      return `<p class="caption">${t('官网栏目包含下列原文，尚待确认它们是随附物料、规格还是其他说明。','These original store rows require review before they can be classified as included items, specifications or other information.')} ${evidenceLink(p.unclassifiedSource||p.url)}</p>`+
        table([t('官网原文','Original store text')],(p.unclassifiedRows||[]).map(row=>[h(Array.isArray(row)?row.join(' · '):row)]));
    }
    if(active==='attributes'){
      const raw=p.attributes||[],model=p.modelSpecs||[];
      if(!raw.length&&!model.length)return emptyRecord(p,false);
      const intro=raw.length?t('以下是该 SKU 的官网 Part List 原表属性。是否随附硬件请查看箱内清单。','These attributes come from the store’s Part List for this SKU. See “In the box” for bundled hardware.'):t('以下配置来自该型号的海外商城商品标题。','These model specifications come from this SKU’s global store product title.');
      const titleEvidence=raw.length&&model.length?`<p class="caption">${t('商城型号标题','Store product title')} · ${h(model.map(a=>attributeLabel(a.name)+' '+a.value).join(' · '))} ${evidenceLink(model[0].source||p.url)}</p>`:'';
      const fields=raw.length?raw:model;
      return `<p class="caption">${intro} ${p.specSource?link(p.specSource,t('官网完整规格 ↗','Full store specifications ↗')):''}</p>`+
        table([t('官网字段','Store field'),t('原始值','Store value'),t('依据','Source')],fields.map(a=>[h(attributeLabel(a.name))+(attributeLabel(a.name)!==a.name?`<small>${h(a.name)}</small>`:'')+(a.group?`<small>${h(a.group)}</small>`:''),h(a.value),evidenceLink(a.source||p.attributeSource||p.url)]))+titleEvidence;
    }
    if(active==='parts'){
      if(!p.parts.length)return emptyRecord(p,true);
      const doc=db.docs[p.partDoc];
      const noQty=p.parts.some(([,q])=>!q);
      const family=p.partEvidenceScope==='family'?t('以下随附物料来自官方系列资料。','The following included items are documented at the product-family level.'):p.partEvidenceScope==='mixed'?t('已合并本型号商品页与官方系列资料，依据逐项标注。','Includes SKU-specific and family-level records. Each row identifies its source.'):'';
      const quantityNote=noQty?t('数量留空表示所引资料未给出数量。','A blank quantity means the source gives no count.'):'';
      return (family||quantityNote?`<p class="caption">${h([family,quantityNote].filter(Boolean).join(' '))}</p>`:'')+
        table([t('随箱物料','Included item'),t('数量','Quantity'),t('依据','Source')],p.parts.map(([n,q])=>[h(n),h(q),evidenceLink(p.partSources?.[n]||p.partSource||(doc?doc.url+'#page=1':p.url))+(p.partScopes?.[n]==='family'?`<small>${t('系列资料','Family scope')}</small>`:'')]));
    }
    if(active==='accessories'){
      if(!p.accessories?.length)return `<div class="record-empty"><p>${t('尚无已核实的选配或扩展件记录。','No optional accessories or expansions have been verified.')}</p>${evidenceLink(p.url)}</div>`;
      const q=state.accFilter.trim().toLowerCase(), rows=(p.accessories||[]).filter(a=>[a.name,a.storeName,a.sku,a.type,a.note].join(' ').toLowerCase().includes(q));
      return `<div class="list-tools"><input id="accfilter" aria-label="${t('筛选配件','Filter accessories')}" placeholder="${t('接口、频段或 SKU','Interface, band or SKU')}" value="${h(state.accFilter)}"><span>${rows.length} ${t('项','items')}</span></div>`+
        table([t('配件及适用条件','Accessory and conditions'),'SKU',t('商城','Store'),t('依据','Source')],rows.map(a=>{
          const target=search.bySku.get(a.sku.toLowerCase()),doc=db.docs[a.doc];
          const evidence=doc?link(doc.url+'#page='+a.page,t('手册第 '+a.printed+' 页 ↗','Manual, printed page '+a.printed+' ↗')):evidenceLink(a.source);
          const scope=a.scope?t(a.scope+' 系列选配',a.scope+' family option'):'';
          return ['<b>'+h(a.storeName||a.name)+'</b><small>'+h([scope,a.type,a.note].filter(Boolean).map(local).join(' · '))+'</small>',target?productLink(target):h(a.sku),target?link(target.url,t('商品页 ↗','Store ↗')):'',evidence];
        }));
    }
    if(active==='notes'){
      const proof=window.Workbench?.customizationInfo(p);
      const rows=proof?[[h(proof.kind),h(proof.text),link(proof.url,t('定制依据 ↗','Service evidence ↗'))]]:
        (p.custom&&p.customUrl?[[t('系列定制','Family services'),h(local(p.custom)),link(p.customUrl,t('系列说明 ↗','Family source ↗'))]]:[]);
      for(const n of p.notes)rows.push([h(local(n.kind)),h(local(n.text)),link(n.source,(n.where?local(n.where):t('原文','Source'))+' ↗')]);
      return table([t('类型','Type'),t('官方说明','Source details'),t('依据','Source')],rows);
    }
    const rows=[[h(p.name),link(p.url,t('海外商城 ↗','Global store ↗'))]];
    if(p.image||p.imageUrl)rows.push([t('产品主图','Product photo'),[link(p.image,t('本地主图 ↗','Local image ↗')),link(p.imageUrl,t('官网图源 ↗','Store image ↗'))].filter(Boolean).join(' · ')]);
    const seen=new Set();
    for(const e of p.wikiEvidence||[]){rows.push([h(e.title),link(e.url,t('已核对的 Wiki ↗','Verified Wiki ↗'))]);seen.add(e.url);}
    for(const d of p.docs){if(!seen.has(d.url)){rows.push([h(d.name),link(d.url,t('打开原文 ↗','Open source ↗'))]);seen.add(d.url);}}
    for(const w of p.wikiLinks||[])if(!seen.has(w.url)){rows.push([h(w.title),link(w.url,t('商品页随附 Wiki ↗','Wiki linked by store ↗'))]);seen.add(w.url);}
    return table([t('文档或来源','Document or source'),t('打开','Open')],rows);
  }
  function renderAssistant(){
    const result=search.lookup(state.query),p=state.pin?search.bySku.get(state.pin.toLowerCase()):result.primary;
    currentProduct=p;currentAlternatives=p?search.alternatives(p,state.query,result.needs):[];
    view.innerHTML=title(t('选型查询','Product finder'),t('从客户指定的产品开始，也可以按应用需求查找。','Start with a named product or search by application requirements.'))+queryForm()+
      (p?`<div class="results"><div class="primary-stack">${mainCard(p,result)}${facts(p)}</div><div class="right-stack">${related(p,currentAlternatives)}</div></div>${information(p)}`:`<div class="empty">${t('没有匹配的产品。可尝试型号、SKU 或具体接口需求。','No matching product. Try a model, SKU or interface requirement.')}</div>`);
  }
  function renderCatalog(){
    let items=db.products.filter(p=>state.group==='*'||(state.group==='menu'?p.groups.length:state.group==='outside'?!p.groups.length:p.groups.includes(state.group)));
    const term=state.catalogQuery.toLowerCase().trim();if(term)items=items.filter(p=>[p.name,p.sku,p.summary,...p.groups,...p.paths.flat()].join(' ').toLowerCase().includes(term));
    const pages=Math.max(1,Math.ceil(items.length/25));state.page=Math.min(state.page,pages);
    const pageItems=items.slice((state.page-1)*25,state.page*25);
    catalogPage={skus:pageItems.slice(0,12).map(p=>p.sku),total:items.length};
    view.innerHTML=title(t('产品目录','Product catalogue'),t('按品类浏览，或使用英文产品名和 SKU 定位。','Browse categories or locate a product by its name and SKU.'))+
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
      return {view,sku:p.sku,tab,query:state.query,filter:tab==='accessories'?state.accFilter:'',alternativeSkus:currentAlternatives.map(r=>r.p.sku)};
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
      `<div class="metrics">${cards.map(([v,l])=>`<div class="panel"><strong>${num(v)}</strong><small>${h(l)}</small></div>`).join('')}</div><div class="panel padded"><h2>${t('字段覆盖','Field coverage')}</h2>`+
      table([t('字段','Field'),t('SKU 数量','SKUs')],[[t('商品 URL','Product URL'),s.urls],[t('正数公开起价','Positive starting price'),s.prices],[t('Part List 原表含属性','Attributes in a Part List section'),attributeCounts.present],[t('已查 Part List 未列属性','Checked Part List contains no attributes'),attributeCounts.empty],[t('Part List 属性原文待核','Part List attribute format requires review'),attributeCounts.unparsed],[t('Part List 尚未核对','Part List not yet checked'),attributeCounts.unread],[t('已另核的商品标题配置','Model configurations verified from store titles'),base.products.filter(p=>p.modelSpecs?.length).length],[t('已列出随箱物料','With in-box items'),s.parts],[t('文档链接','Document links'),s.documents],[t('已读详情专栏','Detail sections read'),s.sections],[t('官方 Wiki 资料或已核事实','Official Wiki links or findings'),s.wikiLinked],[t('有已核对的 Wiki 推荐依据','Verified model-specific Wiki findings'),s.wikiFacts]].map(([l,v])=>[h(l),num(v)]))+
      (reviewRows?`<p class="caption">${h(t(num(reviewProducts)+' 个 SKU 有 '+num(reviewRows)+' 行官网原文待归类，可在这些产品的「原表待核」查看。',num(reviewRows)+' source rows across '+num(reviewProducts)+' SKUs await classification. Open “Rows to review” on those products.'))}</p>`:'')+
      `</div><div class="panel padded"><h2>${t('Products 分类','Products categories')}</h2><p class="caption">${t('同一个 SKU 可能出现在多个分类。','A SKU may appear in multiple categories.')}</p>`+
      table([t('分类','Category'),'SKU',t('已读详情','Details read'),t('有官网属性','Store attributes'),t('有箱内清单','Packing list'),t('官网','Store')],db.categories.map(c=>[`<button class="textbtn" data-group="${h(c.name)}">${h(c.name)}</button>`,num(c.count),num(c.sections),num(c.attributes),num(c.parts),link(c.url,t('打开 ↗','Open ↗'))]))+'</div>';
  }
  function render(){
    if(state.view!=='assistant'){currentProduct=null;currentAlternatives=[];}
    shell();
    if(state.view==='assistant')renderAssistant();
    else if(state.view==='catalog')renderCatalog();
    else if(state.view==='coverage')renderCoverage();
    else if(connected&&window.Workbench)window.Workbench.render(state.view);
    else view.innerHTML=title(t('启动本地工作台','Start the local workspace'),t('双击项目目录中的「启动助手.cmd」继续。','Double-click “Start Assistant.cmd” in the project folder to continue.'));
    syncChat();
  }
  function runQuery(q){
    state.query=q.trim();state.pin='';state.accFilter=/eu868/i.test(q)?'EU868':/us915/i.test(q)?'US915':'';
    state.tab=/随箱|装箱|箱内|in the box|pack(?:ing|age) (?:list|contents)/i.test(q)?'parts':/属性|规格|内存|存储|specifications|attributes|\bstorage\b|\bram\b/i.test(q)?'attributes':state.accFilter||/配件|扩展|wi[ -]?fi|无线网卡|accessor/i.test(q)?'accessories':/定制|logo|customiz/i.test(q)?'notes':'';
    state.view='assistant';history.replaceState(null,'','#assistant');render();
  }
  function route(){
    const hash=location.hash.slice(1);
    if(hash.startsWith('product=')){
      const params=new URLSearchParams(hash);
      const sku=params.get('product'),tab=params.get('tab');
      const p=search.bySku.get(sku.toLowerCase());if(!p){runQuery(sku);return;}
      Object.assign(state,{view:'assistant',pin:p.sku,query:p.sku,accFilter:'',tab:Object.hasOwn(tabs(p),tab)?tab:''});
    }else if(['assistant','catalog','coverage','favorites','custom','developer'].includes(hash))state.view=hash;
    render();window.scrollTo(0,0);
  }
  document.addEventListener('submit',e=>{
    if(e.target.id==='ask'){e.preventDefault();runQuery(el('asktext').value);}
  });
  document.addEventListener('click',e=>{
    const b=e.target.closest('button');if(!b)return;
    if(b.dataset.view){changeView(b.dataset.view);return;}
    if(b.dataset.example){runQuery(b.dataset.example);return;}
    if(b.dataset.tab){
      const jump=!b.closest('.tabs');state.tab=b.dataset.tab;
      if(state.pin)history.replaceState(null,'','#'+new URLSearchParams({product:state.pin,tab:state.tab}));
      const old=document.querySelector('.information');
      if(old&&currentProduct){old.outerHTML=information(currentProduct);if(jump)document.querySelector('.information').scrollIntoView({block:'start',behavior:'smooth'});}
      syncChat();
      return;
    }
    if(b.dataset.group){state.group=b.dataset.group;state.catalogQuery='';state.page=1;changeView('catalog');return;}
    if(b.dataset.page){state.page+=Number(b.dataset.page);renderCatalog();window.scrollTo(0,0);}
  });
  document.addEventListener('change',e=>{if(e.target.id==='category'){state.group=e.target.value;state.page=1;renderCatalog();}});
  document.addEventListener('input',e=>{
    const id=e.target.id,pos=e.target.selectionStart,val=e.target.value;
    if(id==='accfilter'&&currentProduct){state.accFilter=val;el('tabbody').innerHTML=tabBody(currentProduct);syncChat();}
    else if(id==='cattext'){state.catalogQuery=val;state.page=1;renderCatalog();}
    else return;
    const field=el(id);field.focus();field.setSelectionRange(pos,pos);
  });
  async function start(){
    if(location.protocol!=='file:'){
      try{profile=await api('/api/state');lang=profile.language==='en'?'en':'zh-CN';connected=true;}
      catch{connected=false;}
    }
    window.Workbench?.init({api,lang:()=>lang,getDb:()=>db,getState:()=>profile,getProduct:sku=>search?.bySku.get(String(sku).toLowerCase()),
      view,sidebar:el('sidebar-favorites'),openProduct,changeView,reloadData,onLanguage:snapLang,renderApp:render,onContextChange:syncChat});
    rebuild();
    window.WorkbenchChat?.init({root:el('global-ai'),api,language:()=>lang,connected:()=>connected,profile:()=>({provider:profile.provider,providers:profile.providers}),
      getContext:chatContext,getContextLabel:chatContextLabel,openSettings:()=>window.Workbench?.openSettings(),
      openEvidence:openChatEvidence,openProject:id=>window.Workbench?.openProject(id),openProduct});
    window.addEventListener('hashchange',route);route();
  }
  start();
})();
