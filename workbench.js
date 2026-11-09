(() => {
  'use strict';

  let app;
  const customTypes = new Set(['favorites', 'custom', 'developer']);
  const pageSize = 20;
  const ui = {
    view: '', activeDev: 'settings', selectedFavorites: new Set(), targetProject: '',
    filterSku: '', customFilter: '', customPage: 1, projectDraft: null,
    editor: null, editorQuery: '', provider: '', update: null, updateTimer: null,
    changes: new Set(), diffQuery: '', diffPage: 1, refreshSkus: '', refreshCategory: '', imageSearch:'',
    notice: '', noticeError: false, busy: new Set()
  };
  const L = (zh, en) => app.lang() === 'en' ? en : zh;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => (
    {'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]
  ));
  const safeUrl = value => {
    if (!value) return '';
    try {
      const url = new URL(value);
      if (url.protocol === 'https:' || url.protocol === 'http:') return url.href;
    } catch { /* A source link must contain a full external URL. */ }
    return '';
  };
  const imageUrl = value => /^(?:\.?\/?data\/jpg\/|\/user-images\/)[\w.-]+\.jpe?g$/i.test(value || '') ? value : safeUrl(value);
  const thumb = p => {
    const url = imageUrl(p.image || p.imageUrl);
    return url ? `<img class="wb-thumb" src="${esc(url)}" alt="" loading="lazy">` : '';
  };
  const store = () => app.getState?.() || {};
  const db = () => app.getDb();
  const products = () => db().products;
  const getProduct = sku => app.getProduct(sku);
  const favorites = () => store().favorites || [];
  const projects = () => store().projects || [];
  const txt = (id, text, attrs = '') => `<button type="button" class="wb-text" data-wb-action="${id}" ${attrs}>${esc(text)}</button>`;
  const attr = (key, value) => `data-wb-${key}="${esc(value)}"`;
  const primary = (id, text, attrs = '') => `<button type="button" class="wb-button wb-primary" data-wb-action="${id}" ${attrs}>${esc(text)}</button>`;
  const button = (id, text, attrs = '') => `<button type="button" class="wb-button" data-wb-action="${id}" ${attrs}>${esc(text)}</button>`;
  const pageTitle = (name, desc) => `<div class="page-title"><h1>${esc(name)}</h1><p>${esc(desc)}</p></div>`;
  const input = (id, label, value, attrs='') => `<label class="wb-field"><span>${esc(label)}</span><input id="${id}" value="${esc(value)}" ${attrs}></label>`;
  const source = (url, label) => safeUrl(url) ? `<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>` : '';
  const open = (p, label='') => txt('open', label || p.name, attr('sku',p.sku));
  const uniq = array => [...new Set(array)];
  const splitList = s => uniq(s.split(/[,，;；\n]+/).map(x=>x.trim()).filter(Boolean));
  const noticeBox = () => `<div id="wb-notice" role="status" aria-live="polite" class="wb-notice${ui.noticeError?' wb-error':''}" ${ui.notice?'':'hidden'}>${esc(ui.notice)}</div>`;
  function notify(message, error=false) {
    ui.notice=message;ui.noticeError=error;
    let box=document.getElementById('wb-notice');
    if(!box){
      box=document.createElement('div');box.id='wb-notice';box.setAttribute('role','status');box.setAttribute('aria-live','polite');
      app.view.prepend(box);
    }
    box.textContent=message;box.className='wb-notice'+(error?' wb-error':'');box.hidden=!message;
  }
  function errorText(err) {
    const code=String(err?.code || err?.message || '').toLowerCase();
    if(/csrf|unauthor|origin|session/.test(code))return L('会话已过期，请刷新页面后重试。','The session expired. Reload the page and try again.');
    if(/sku.*exist|duplicate/.test(code))return L('此 SKU 已存在，请在“编辑产品”中打开。','This SKU already exists. Open it in Edit product.');
    if(/custom|ineligible/.test(code))return L('所选 SKU 需要公开的定制依据，或先在产品编辑中人工确认。','The SKU needs documented customization support or manual confirmation in the product editor.');
    if(/image|file|larg[ei]|jpeg|upload/.test(code))return L('图片格式或大小未通过校验，请换一张较小的 JPG、PNG 或 WebP 图片。','The image could not be saved. Try a smaller JPEG, PNG or WebP image.');
    if(/429|rate.?limit|cooldown/.test(code))return L('官网正在限速，进度已保留。请等待冷却结束再续跑。','The store is rate-limiting requests. Progress was saved. Resume after the cooldown.');
    if(/busy|running|conflict/.test(code))return L('已有同步任务正在运行。','A sync job is already running.');
    if(/invalid|unknown|missing.*sku|no.*change|selection/.test(code))return L('请检查所填字段、SKU 和选择范围。','Check the fields, SKUs and selected scope.');
    if(/offline|network|fetch|service|unavailable|failed to|local/.test(code))return L('未连接到本地服务，请使用项目启动器打开工作台。','The local service is unavailable. Open the workbench using its launcher.');
    return L('操作未完成。请检查输入或本地服务状态后重试。','The operation did not finish. Check the inputs and local service, then try again.');
  }
  function customInfo(p) {
    if(!p)return null;
    const state=store(),overlay=state.overrides?.[p.sku];
    if(Array.isArray(state.customizableSkus)&&!state.customizableSkus.includes(p.sku))return null;
    if(p.customConfirmed===true || overlay?.customConfirmed===true)
      return {text:overlay?.custom || p.custom || L('项目经理已确认','Confirmed by a project manager'),url:'',kind:L('人工确认','Manually confirmed')};
    if(state.customEvidence){
      const evidence=state.customEvidence[p.sku];
      if(!evidence || !safeUrl(evidence.url))return null;
      const text=typeof localizedProductText==='function'?localizedProductText(evidence.text,app.lang()):evidence.text;
      return {text,url:evidence.url,kind:evidence.kind==='series'?L('系列官方资料','Official series documentation'):L('商品页说明','Product documentation')};
    }
    const official=overlay?.custom!==undefined
      ? (window.SEEED_CATALOG?.products.find(it=>it.sku===p.sku)||p) : p;
    if(official.custom && safeUrl(official.customUrl)) {
      const text=typeof localizedProductText==='function'?localizedProductText(official.custom,app.lang()):official.custom;
      return {text,url:official.customUrl,kind:L('系列官方资料','Official series documentation')};
    }
    return null;
  }
  const eligible = p => !!customInfo(p);
  const customProducts = () => products().filter(eligible);
  const favoritePreference='seeed-workbench.favorites-sidebar.expanded';
  let favoriteExpanded;
  function favoritesOpen(){
    if(favoriteExpanded===undefined){
      let saved=null;
      try{saved=localStorage.getItem(favoritePreference);}catch{}
      favoriteExpanded=saved===null?window.matchMedia('(min-width:991px)').matches:saved==='true';
    }
    return favoriteExpanded;
  }
  function sidebarFavorites() {
    if(!app?.sidebar)return;
    const items=favorites().map(getProduct).filter(Boolean);
    const expanded=favoritesOpen();
    const toggleName=expanded?L('收起收藏夹','Collapse favorites'):L('展开收藏夹','Expand favorites');
    app.sidebar.innerHTML=`<div class="wb-side-label"><button id="wb-fav-toggle" type="button" aria-label="${toggleName}" title="${toggleName}" aria-expanded="${expanded}" aria-controls="wb-fav-list"><span aria-hidden="true"></span></button>${txt('favorites',L('收藏夹','Favorites'))}<span>${items.length}</span></div><div id="wb-fav-list" ${expanded?'':'hidden'}>`+
      (items.length?`<ul>${items.slice(0,6).map(p=>`<li>${txt('open',p.name,attr('sku',p.sku)+' title="'+esc(p.sku+' · '+p.name)+'"')}</li>`).join('')}</ul>`
                    :`<small>${L('在产品卡片点 ☆ 收藏','Choose ☆ on a product card to save it.')}</small>`)+
      (items.length>6?txt('favorites',L('查看全部收藏','View all favorites')):'')+'</div>';
  }
  function productActions(sku) {
    const p=getProduct(sku);if(!p)return '';
    const saved=favorites().includes(p.sku);
    const n=projects().filter(x=>x.skus?.includes(p.sku)).length;
    return `<div class="wb-product-actions">${button('star',saved?L('★ 已收藏','★ Saved'):L('☆ 收藏','☆ Save'),attr('sku',sku)+' aria-pressed="'+saved+'"')}
      ${eligible(p)||n?button('custom-for',L('相关定制','Customization')+(n?' · '+n:''),attr('sku',sku)):''}</div>`;
  }
  function changeView(id) {
    ui.notice='';app.changeView(id);
    if(ui.view===id && active())paint();
  }
  function openCustomFor(sku) {
    ui.filterSku=sku;ui.customFilter='';ui.customPage=1;ui.projectDraft=null;
    changeView('custom');
  }
  function active() {
    return !!document.getElementById('wb-workbench') && customTypes.has(ui.view);
  }
  function favPage() {
    const list=favorites().map(getProduct).filter(Boolean);
    const allowed=list.filter(eligible);
    ui.selectedFavorites=new Set([...ui.selectedFavorites].filter(s=>allowed.some(p=>p.sku===s)));
    const count=ui.selectedFavorites.size;
    const opts=projects().map(x=>`<option value="${esc(x.id)}" ${x.id===ui.targetProject?'selected':''}>${esc(x.title)}</option>`).join('');
    return pageTitle(L('收藏夹','Favorites'),L('打开已收藏产品，或把可定制的产品加入同一个需求。','Reopen saved products and add eligible SKUs to a customization project.'))+
      (list.length?`<div class="panel wb-panel"><div class="wb-heading"><h2>${L('已收藏产品','Saved products')} <small>${list.length}</small></h2></div>
      <div class="wb-collection-actions"><label><input type="checkbox" id="wb-allfav" ${allowed.length&&count===allowed.length?'checked':''} ${allowed.length?'':'disabled'}> ${L('全选可定制产品','Select eligible products')}</label>
      <select id="wb-target-project" aria-label="${L('目标定制需求','Target project')}"><option value="">${L('新建定制需求','New project')}</option>${opts}</select>
      ${primary('favorites-project',L('加入定制需求','Add to project')+(count?' ('+count+')':''),count?'':'disabled')}</div>
      <ul class="wb-products">${list.map(p=>`<li><input aria-label="${esc(L('选择 ','Select ')+p.sku)}" type="checkbox" data-wb-fav-check="${esc(p.sku)}" ${ui.selectedFavorites.has(p.sku)?'checked':''} ${eligible(p)?'':'disabled'}>
      ${thumb(p)}<div class="wb-item-name">${open(p)}<small>${esc(p.sku)} · ${eligible(p)?L('可定制','Customization available'):L('定制能力未确认','Customization unconfirmed')}</small></div>
      ${eligible(p)?txt('custom-for',L('相关定制','Customization'),attr('sku',p.sku)):''}${txt('star',L('取消收藏','Remove'),attr('sku',p.sku))}</li>`).join('')}</ul></div>`:
      `<div class="panel wb-panel wb-empty"><p>${L('收藏夹为空。打开一个产品，再点“☆ 收藏”。','No saved products yet. Open a product and choose ☆ Save.')}</p>${button('catalog',L('打开产品目录','Browse catalog'))}</div>`);
  }
  function newDraft(skus=[]) {
    return {id:'',title:'',description:'',labels:'',skus:uniq(skus),picker:''};
  }
  function editProject(id) {
    const p=projects().find(x=>x.id===id);if(!p)return;
    ui.projectDraft={id:p.id,title:p.title,description:p.description||'',labels:(p.labels||[]).join(', '),skus:[...(p.skus||[])],picker:''};
  }
  function openProject(id){
    if(!projects().some(p=>p.id===id))return false;
    ui.filterSku='';editProject(id);
    changeView('custom');
    document.getElementById('wb-project-title')?.focus();
    return true;
  }
  const match=(p,q)=>!q || (p.sku+' '+p.name).toLowerCase().includes(q.toLowerCase().trim());
  function projectChoices() {
    const d=ui.projectDraft;if(!d)return '';
    const options=customProducts().filter(p=>!d.skus.includes(p.sku)&&match(p,d.picker));
    return options.slice(0,8).map(p=>button('member-add',p.sku+' · '+p.name,attr('sku',p.sku))).join('')||
      `<small>${L('没有匹配的可定制产品。','No eligible products match.')}</small>`;
  }
  function projectEditor(){
    const d=ui.projectDraft;
    return `<form class="panel wb-panel wb-editor" id="wb-project-form"><div class="wb-heading"><h2>${d.id?L('编辑定制需求','Edit project'):L('新建定制需求','New project')}</h2>${txt('cancel-project',L('取消','Cancel'))}</div>
      ${input('wb-project-title',L('需求标题','Project title'),d.title,'required maxlength="180" data-wb-draft="title"')}
      <label class="wb-field"><span>${L('需求描述','Requirements')}</span><textarea id="wb-project-description" rows="3" maxlength="12000" data-wb-draft="description">${esc(d.description)}</textarea></label>
      ${input('wb-project-labels',L('标签（逗号分隔）','Labels (comma-separated)'),d.labels,'maxlength="2000" data-wb-draft="labels"')}
      <div><b>${L('关联产品','Linked products')}</b><div class="wb-chips">${d.skus.map(s=>`<span>${esc(s)} ${txt('member-remove','×',attr('sku',s)+' aria-label="'+esc(L('移除 ','Remove ')+s)+'"')}</span>`).join('')||`<small>${L('请至少选择一个可定制 SKU。','Choose at least one eligible SKU.')}</small>`}</div>
      ${input('wb-member-search',L('查找可定制产品','Find an eligible product'),d.picker,'data-wb-draft="picker"')}
      <div id="wb-member-options" class="wb-picker">${projectChoices()}</div></div>
      <div class="wb-actions"><button class="wb-button wb-primary" type="submit">${L('保存定制需求','Save project')}</button></div></form>`;
  }
  function projectCards(){
    const list=projects().filter(x=>!ui.filterSku||x.skus.includes(ui.filterSku));
    if(!list.length)return `<div class="wb-empty">${ui.filterSku?L('这款产品还没有关联需求。','No projects linked to this SKU.'):L('还没有定制需求。','No customization projects yet.')}</div>`;
    return `<div class="wb-project-list">${list.map(p=>`<article><div class="wb-heading"><h3>${esc(p.title)}</h3><div>${txt('edit-project',L('编辑','Edit'),attr('id',p.id))} ${txt('delete-project',L('删除','Delete'),attr('id',p.id))}</div></div>
      ${p.description?`<p>${esc(p.description)}</p>`:''}
      ${(p.labels||[]).length?`<div class="wb-chips">${p.labels.map(s=>`<span>${esc(s)}</span>`).join('')}</div>`:''}
      <div class="wb-members">${p.skus.map(s=>{const m=getProduct(s);return m?open(m,s+' · '+m.name):esc(s);}).join('')}</div></article>`).join('')}</div>`;
  }
  function filteredEligible(){
    return customProducts().filter(p=>(!ui.filterSku||ui.filterSku===p.sku)&&match(p,ui.customFilter));
  }
  function eligibleList(){
    const list=filteredEligible();
    const last=Math.max(1,Math.ceil(list.length/pageSize));ui.customPage=Math.min(ui.customPage,last);
    return `<ul class="wb-products">${list.slice((ui.customPage-1)*pageSize,ui.customPage*pageSize).map(p=>{
      const info=customInfo(p);
      return `<li>${thumb(p)}<div class="wb-item-name">${open(p)}<small>${esc(p.sku)} · ${esc(info.kind)} ${source(info.url,L('来源','Source'))}</small><p>${esc(info.text)}</p></div>
        ${txt('new-from-sku',L('创建需求','New project'),attr('sku',p.sku))}</li>`;
    }).join('')}</ul>${list.length?'':`<p class="wb-empty">${L('没有符合条件的产品。','No matching eligible products.')}</p>`}
    ${last>1?`<div class="wb-pager">${button('custom-prev',L('上一页','Previous'),ui.customPage===1?'disabled':'')}<small>${ui.customPage} / ${last}</small>${button('custom-next',L('下一页','Next'),ui.customPage===last?'disabled':'')}</div>`:''}`;
  }
  function customPage(){
    const p=ui.filterSku && getProduct(ui.filterSku);
    return pageTitle(L('定制服务','Customization'),L('管理客户的定制需求，关联有官方依据或经人工确认的 SKU。','Manage customer requirements with documented or manually confirmed products.'))+
      (p?`<div class="wb-filter-chip">${esc(p.sku+' · '+p.name)} ${txt('clear-custom',L('查看全部','Show all'))}</div>`:'')+
      (ui.projectDraft?projectEditor():'')+
      `<section class="panel wb-panel"><div class="wb-heading"><h2>${L('定制需求','Projects')}</h2>${primary('new-project',L('新建需求','New project'))}</div>${projectCards()}</section>
      <section class="panel wb-panel"><div class="wb-heading"><h2>${L('可定制产品','Eligible products')}</h2>
      <input id="wb-custom-filter" aria-label="${L('筛选可定制产品','Filter eligible products')}" placeholder="${L('搜索名称或 SKU','Search by name or SKU')}" value="${esc(ui.customFilter)}"></div>
      <div id="wb-eligible-list">${eligibleList()}</div></section>`;
  }

  function providerForm() {
    const cfg=store();
    const provider=ui.provider || cfg.provider || 'deepseek';
    const prefs=cfg.providers?.[provider] || {};
    const seen=prefs.hasKey;
    return `<section class="panel wb-panel"><div class="wb-heading"><h2>${L('界面语言','Interface language')}</h2>
      <select id="wb-language" aria-label="${L('界面语言','Interface language')}"><option value="zh" ${app.lang()!=='en'?'selected':''}>简体中文</option><option value="en" ${app.lang()==='en'?'selected':''}>English</option></select></div></section>
      <form class="panel wb-panel wb-editor" id="wb-provider-form" autocomplete="off"><div class="wb-heading"><h2>${L('AI 服务','AI provider')}</h2><small>${L('当前提供商','Active provider')} · ${cfg.provider==='doubao'?'Doubao':'DeepSeek'}</small></div>
      <div class="wb-grid2"><label class="wb-field"><span>${L('提供商','Provider')}</span><select id="wb-provider"><option value="deepseek" ${provider==='deepseek'?'selected':''}>DeepSeek</option><option value="doubao" ${provider==='doubao'?'selected':''}>${L('豆包（火山方舟）','Doubao (Volcengine Ark)')}</option></select></label>
      ${input('wb-model',provider==='doubao'?L('模型或推理 Endpoint ID','Model or endpoint ID'):L('模型','Model'),prefs.model||'','maxlength="160" autocomplete="off"')}</div>
      <label class="wb-field"><span>${L('API 密钥','API key')} <small>${seen?L('已配置','Configured'):L('未配置','Not configured')}</small></span>
        <input id="wb-key" type="password" autocomplete="new-password" spellcheck="false" placeholder="${seen?L('留空保留已保存的密钥','Leave empty to keep the saved key'):L('输入此提供商的密钥','Enter a key for this provider')}"></label>
      <small>${L('密钥保存在此设备上。在 AI 对话中发送消息时，才会请求提供商。','The key stays on this device. The app contacts the model provider when you send a chat message.')}</small>
      <div class="wb-actions"><button class="wb-button wb-primary" type="submit">${L('保存 AI 设置','Save AI settings')}</button>${seen?txt('clear-key',L('移除此提供商的密钥','Remove key for this provider')):''}</div></form>`;
  }
  function defaultEditor(p=null) {
    return {create:!p, sku:p?.sku||'', name:p?.name||'', summary:p?.summary||'', url:p?.url||'',
      price:p?.price == null?'':String(p.price),currency:p?.currency||'USD',image:p?.image||p?.imageUrl||'',
      imageInput:p?.image||p?.imageUrl||'',imageData:'',manual:!!p?.customConfirmed||!!store().overrides?.[p?.sku]?.customConfirmed,
      custom:store().overrides?.[p?.sku]?.custom||'',original:p};
  }
  function editorMatches() {
    const q=ui.editorQuery.trim();
    if(!q) return '';
    const list=products().filter(p=>match(p,q)).sort((a,b)=>Number(b.sku.toLowerCase()===q.toLowerCase())-Number(a.sku.toLowerCase()===q.toLowerCase())).slice(0,7);
    return list.map(p=>button('edit-sku',p.sku+' · '+p.name,attr('sku',p.sku))).join('')||
      `<small>${L('没有找到现有 SKU。可使用“新增产品”。','No existing SKU found. Use Add product to create one.')}</small>`;
  }
  function imageMatches(){
    const q=ui.imageSearch.trim();
    if(!q)return '';
    const found=products().filter(p=>match(p,q)&&imageUrl(p.image||p.imageUrl)).slice(0,6);
    return found.map(p=>button('use-image',p.sku+' · '+p.name,attr('sku',p.sku))).join('')||
      `<small>${L('没有找到带主图的产品。','No matching product with an image.')}</small>`;
  }
  function skuEditor(){
    const d=ui.editor;
    if(!d)return '';
    const image=d.imageData||imageUrl(d.imageInput);
    return `<form class="panel wb-panel wb-editor" id="wb-sku-form"><div class="wb-heading"><h2>${d.create?L('新增产品','Add product'):L('编辑产品','Edit product')}</h2>${txt('cancel-editor',L('关闭编辑','Close editor'))}</div>
      <div class="wb-grid2">${input('wb-sku','SKU',d.sku,'required maxlength="100" data-wb-editor="sku" '+(d.create?'':'readonly'))}
      ${input('wb-name',L('产品名称','Product name'),d.name,'required maxlength="500" data-wb-editor="name"')}</div>
      ${input('wb-url',L('商品 URL','Product URL'),d.url,'type="url" data-wb-editor="url"')}
      <label class="wb-field"><span>${L('产品描述','Description')}</span><textarea id="wb-summary" rows="4" maxlength="12000" data-wb-editor="summary">${esc(d.summary)}</textarea></label>
      <div class="wb-grid2">${input('wb-price',L('参考价格','Reference price'),d.price,'type="number" min="0" step="any" data-wb-editor="price"')}
      ${input('wb-currency',L('币种','Currency'),d.currency,'pattern="[a-zA-Z]{3}" maxlength="3" data-wb-editor="currency"')}</div>
      <fieldset><legend>${L('产品主图','Product image')}</legend><div class="wb-image-edit"><div id="wb-image-preview">${image?`<img alt="${L('主图预览','Image preview')}" src="${esc(image)}">`:''}</div><div>
      ${input('wb-image-input',L('已有主图地址','Existing image URL or local catalog image path'),d.imageInput,'data-wb-editor="imageInput"')}
      <details class="wb-reuse"><summary>${L('使用目录中已有的主图','Use an existing catalog image')}</summary>
        ${input('wb-image-search',L('搜索图片所属产品','Find the product that owns the image'),ui.imageSearch)}<div id="wb-image-results" class="wb-picker">${imageMatches()}</div></details>
      <label class="wb-field"><span>${L('上传替换图片','Upload a replacement')}</span><input type="file" id="wb-image-file" accept="image/jpeg,image/png,image/webp"></label>
      <small>${L('支持 JPG、PNG、WebP；上传时转换为一张 JPG 主图。','JPEG, PNG and WebP uploads are saved as one JPEG product image.')}</small></div></div></fieldset>
      <fieldset><legend>${L('定制资格','Customization eligibility')}</legend><label><input type="checkbox" id="wb-manual" ${d.manual?'checked':''}> ${L('已人工确认此 SKU 可提供定制服务','I have confirmed that this SKU supports a customization service')}</label>
      ${input('wb-custom-note',L('人工核实的服务或依据','Confirmed service or supporting note'),d.custom,'maxlength="2000" data-wb-editor="custom"')}</fieldset>
      <div class="wb-actions"><button class="wb-button wb-primary" type="submit">${L('保存产品','Save product')}</button></div></form>`;
  }
  function productsTab(){
    const edited=Object.keys(store().overrides||{}).map(getProduct).filter(Boolean);
    return `<section class="panel wb-panel"><div class="wb-heading"><h2>${L('编辑产品资料','Edit product records')}</h2>${primary('new-sku',L('新增产品','Add product'))}</div>
      <p class="caption">${L('手工修改单独保存，官网同步后仍优先显示。','Local edits are stored separately and take priority after a catalog sync.')}</p>
      ${input('wb-edit-query',L('按 SKU 或名称查找要编辑的产品','Find a product by SKU or name'),ui.editorQuery)}
      <div id="wb-edit-results" class="wb-picker">${editorMatches()}</div></section>
      ${skuEditor()}${edited.length?`<section class="panel wb-panel"><h2>${L('已人工修改','Locally edited products')}</h2><ul class="wb-products">${edited.map(p=>`<li>${thumb(p)}<div class="wb-item-name">${open(p)}<small>${esc(p.sku)}</small></div>${txt('edit-sku',L('编辑','Edit'),attr('sku',p.sku))}</li>`).join('')}</ul></section>`:''}`;
  }
  const fieldNames = {
    name:['名称','Name'], sku:['SKU','SKU'], summary:['简介','Description'], description:['描述','Description'],url:['商品链接','URL'],
    groups:['分类','Categories'],categories:['分类','Categories'],paths:['分类路径','Category paths'],price:['价格','Price'],currency:['币种','Currency'],
    image:['主图','Image'],imageUrl:['主图源地址','Image URL'],maxPrice:['最高价','Maximum price'],parts:['箱内清单','Box contents'],
    notes:['说明','Notes'],docs:['文档','Documents'],accessories:['配件','Accessories'],custom:['定制','Customization'],
    'new':['新增','New'],changed:['有变化','Changed'],missing:['本次未出现','Missing from snapshot']
  };
  const statusNames={idle:['等待操作','Idle'],running:['进行中','Running'],ready:['预览就绪','Preview ready'],done:['已完成','Complete'],
    paused:['已暂停','Paused'],error:['出现错误','Error'],failed:['出现错误','Failed']};
  const phaseNames={preview:['差异预览','Preview'],apply:['应用更新','Apply changes'],refresh:['重抓资料','Refresh records'],resume:['恢复','Resume'],
    inventory:['读取目录','Read inventory'],catalog:['读取目录','Read catalog'],fetch:['读取资料','Fetch records'],details:['读取详情','Read details'],
    images:['处理主图','Process images'],write:['保存结果','Save records'],saving:['保存结果','Save records'],commit:['提交更新','Commit changes'],
    diff:['比较差异','Compare snapshots'],categories:['核对分类','Check categories'],compare:['比较差异','Compare snapshots'],
    cooldown:['等待冷却','Cooldown'],complete:['完成','Complete'],done:['完成','Done'],start:['开始','Starting'],scan:['检查目录','Scan catalog']};
  const phrase=(map,key,fallback='')=>map[key]?L(...map[key]):fallback;
  function formatDate(value) {
    if(!value)return '';
    if(typeof value==='string' && /^\d{4}-\d{2}-\d{2}$/.test(value))return value;
    const raw=typeof value==='number'&&value<1e12?value*1000:value;
    const date=new Date(raw);
    return Number.isNaN(date.getTime())?'':new Intl.DateTimeFormat(app.lang()==='en'?'en-US':'zh-CN',{dateStyle:'medium',timeStyle:'short'}).format(date);
  }
  function updateStatus(){
    const j=ui.update;
    if(!j)return `<p class="caption">${L('正在读取本地同步状态…','Reading local sync status…')}</p>`;
    const st=phrase(statusNames,j.status,L('状态待确认','Status unavailable'));
    const phase=phrase(phaseNames,j.phase,phrase(phaseNames,j.action));
    const n=Number(j.done)||0,total=Number(j.total)||0;
    const originalDate=(db().products||[]).find(p=>p.updated)?.updated || '';
    return `<div class="wb-jobline"><strong>${esc(st)}</strong>${phase?`<span>${esc(phase)}</span>`:''}${total?`<span>${n} / ${total}</span>`:''}
      ${j.status==='paused'||(j.status==='error'&&j.remaining>0)?button('resume-job',L('续跑上次任务','Resume job')):''}</div>
      ${total?`<progress max="${total}" value="${n}" aria-label="${esc(st)}"></progress>`:''}
      <dl class="wb-sync-dates"><div><dt>${L('上次检查官网','Last store check')}</dt><dd>${esc(formatDate(j.lastCheckedAt)||L('尚未检查','Not checked yet'))}</dd></div>
      <div><dt>${L('上次成功写入商品','Last successful catalog write')}</dt><dd>${esc(formatDate(j.lastAppliedAt||originalDate)||'—')}</dd></div></dl>
      ${j.retryAt?`<small>${L('可续跑时间','Resume after')} · ${esc(formatDate(j.retryAt))}</small>`:''}
      ${j.warningCount?`<details class="wb-warnings"><summary>${L('待核项目','Items to review')} · ${Number(j.warningCount)}</summary><ul>${(j.warnings||[]).map(w=>`<li>${esc(w.sku)} · ${esc(warningText(w.code))}</li>`).join('')}</ul></details>`:''}
      ${j.error?`<p class="wb-error">${esc(updateError(j.error))}</p>`:''}`;
  }
  function warningText(code){
    const labels={NOT_IN_CURRENT_STORE:['本次检索未出现','Missing from the current store search'],NO_PRODUCT_URL:['没有可核实的商品页','No verified product page'],
      NO_NEW_SECTIONS:['商品页未返回详情专栏','No product detail sections returned'],IMAGE_FAILED:['主图未更新','Image update failed'],
      ROBOTS_UNVERIFIED:['暂时无法核对官网抓取规则','The store crawler rules could not be verified'],ROBOTS_EXCLUDED:['官网规则排除了这个地址','Store rules exclude this URL'],
      DETAIL_SKU_NOT_VERIFIED:['官网页面的 SKU 身份未核实','The SKU on the store page could not be verified'],STORE_HTTP_404:['此商品页返回 HTTP 404','The product page returned HTTP 404'],
      STORE_API_CHANGED:['官网返回的数据结构有变化','The store data structure changed']};
    return phrase(labels,code,L('原有资料已保留','Previous information preserved'))+(code?' ('+code+')':'');
  }
  function updateError(error) {
    const normalized=String(error?.code||error).toLowerCase();
    if(normalized==='robots_unverified')return L('暂时无法核对官网抓取规则。任务已暂停，可在官网恢复后续跑。','The crawler rules could not be verified. The job has stopped and can resume when the source recovers.');
    if(normalized==='store_http_403')return L('官网拒绝了本次访问。此前完成的资料已保留。','The store denied this request. Completed records remain available.');
    if(/429|limit|paused|cooldown/.test(normalized))return L('官网限速。已保存进度，可在冷却结束后续跑。','The official store requested a cooldown. Saved progress can be resumed afterwards.');
    if(/network|upstream|http|fetch|timeout|remote/.test(normalized))return L('官网数据暂时不可用，已保留上次目录。','The store is unavailable. The previous catalog is preserved.');
    if(/interrupt/.test(normalized))return L('上一次任务中断，可从已保存的位置续跑。','The previous job was interrupted. Resume from its saved checkpoint.');
    if(/api_changed/.test(normalized))return L('官网数据结构有变化。请检查同步脚本。','The store response format changed. Review the synchronization script.');
    return errorText({code:normalized});
  }
  const changes=()=>ui.update?.changes||[];
  function diffFields(change){
    const keys=change.fields||[];
    if(!keys.length)return '';
    const fmt=v=>v==null||v===''?'—':Array.isArray(v)?v.map(x=>Array.isArray(x)?x.join(' › '):String(x)).join(', '):String(v);
    const details=keys.filter(k=>change.diff?.[k]);
    const caption=esc(keys.map(k=>phrase(fieldNames,k,k)).join(', '));
    if(!details.length)return caption;
    return `<details class="wb-diff"><summary>${caption}</summary>${details.map(k=>`<div><b>${esc(phrase(fieldNames,k,k))}</b><small>${L('原值','Before')} · ${esc(fmt(change.diff[k].before))}</small><small>${L('新值','After')} · ${esc(fmt(change.diff[k].after))}</small></div>`).join('')}</details>`;
  }
  function diffRows(){
    const lines=changes().filter(c=>!ui.diffQuery||(c.sku+' '+(c.name||'')).toLowerCase().includes(ui.diffQuery.toLowerCase()));
    const pages=Math.max(1,Math.ceil(lines.length/pageSize));ui.diffPage=Math.min(ui.diffPage,pages);
    const chosen=ui.changes.size;
    return `<div class="wb-collection-actions"><label><input type="checkbox" id="wb-select-diff" ${lines.some(c=>c.kind!=='missing')&&lines.filter(c=>c.kind!=='missing').every(c=>ui.changes.has(c.sku))?'checked':''} ${!lines.some(c=>c.kind!=='missing')?'disabled':''}>
       ${L('选择筛选结果','Select filtered changes')}</label>${primary('apply-job',L('应用选中变更','Apply selected changes')+(chosen?' ('+chosen+')':''),!chosen||ui.update?.status!=='ready'?'disabled':'')}</div>
      <div class="table-scroll"><table><thead><tr><th></th><th>SKU</th><th>${L('产品','Product')}</th><th>${L('变化','Change')}</th><th>${L('字段','Fields')}</th></tr></thead><tbody>
      ${lines.slice((ui.diffPage-1)*pageSize,ui.diffPage*pageSize).map(c=>`<tr><td><input type="checkbox" aria-label="${esc(c.sku)}" data-wb-diffsku="${esc(c.sku)}" ${ui.changes.has(c.sku)?'checked':''} ${c.kind==='missing'?'disabled':''}></td>
      <td>${esc(c.sku)}</td><td>${esc(c.name)}</td><td>${esc(phrase(fieldNames,c.kind,c.kind))}</td><td>${diffFields(c)}</td></tr>`).join('')}</tbody></table></div>
      ${pages>1?`<div class="wb-pager">${button('diff-prev',L('上一页','Previous'),ui.diffPage===1?'disabled':'')}<span>${ui.diffPage} / ${pages}</span>${button('diff-next',L('下一页','Next'),ui.diffPage===pages?'disabled':'')}</div>`:''}
      ${lines.length?'':`<p class="caption">${ui.update?.status==='ready'?L('当前预览中没有匹配的差异。','No matching differences in this preview.'):L('检查官网目录后，差异会显示在这里。','Check the official catalog to populate the preview.')}</p>`}`;
  }
  function updateTab(){
    const running=ui.update?.status==='running';
    return `<section class="panel wb-panel"><div class="wb-heading"><h2>${L('目录同步','Catalog sync')}</h2>${primary('preview-job',L('检查新增与差异','Check for changes'),running?'disabled':'')}</div>
      <div id="wb-job-status">${updateStatus()}</div><p class="caption">${L('脚本对照官网公开目录与本地数据。官网限速、网页结构变化和缺少型号依据，都可能留下待核字段。','The sync compares public store records with local data. Rate limits, page layout changes and ambiguous models can leave fields unresolved.')}</p></section>
      <section class="panel wb-panel"><div class="wb-heading"><h2>${L('变更预览','Change preview')}</h2><input id="wb-diff-query" value="${esc(ui.diffQuery)}" aria-label="${L('筛选差异','Filter changes')}" placeholder="${L('查找名称或 SKU','Filter by name or SKU')}"></div><div id="wb-diff-list">${diffRows()}</div></section>
      <section class="panel wb-panel wb-editor"><h2>${L('按范围重抓','Refresh a scope')}</h2><div class="wb-grid2">
      ${input('wb-refresh-skus',L('一个或多个 SKU（逗号分隔）','One or more SKUs (comma-separated)'),ui.refreshSkus)}
      <label class="wb-field"><span>${L('或选择官方分类','Or select a category')}</span><select id="wb-refresh-category"><option value="">${L('选择分类','Select a category')}</option>
      ${db().categories.map(c=>`<option value="${esc(c.name)}" ${ui.refreshCategory===c.name?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label></div>
      <div class="wb-actions">${button('refresh-subset',L('重抓选定 SKU / 分类','Refresh selected SKUs / category'),running?'disabled':'')}</div></section>
      <section class="panel wb-panel"><div class="wb-heading"><div><h2>${L('全量重抓','Refresh entire catalog')}</h2><small>${L('检查全目录，按 SKU 更新公开资料和主图。人工修改、收藏和定制需求继续保留。','Refresh public records and main images across the catalog. Local edits, favorites and projects are preserved.')}</small></div>${button('refresh-all',L('一键全量重抓','Run full refresh'),running?'disabled':'')}</div></section>`;
  }
  function developerPage() {
    const nav=[['settings',L('语言与 AI','Language & AI')],['products',L('产品编辑','Product editor')],['updates',L('目录更新','Catalog updates')]];
    return pageTitle(L('开发者设置','Developer settings'),L('管理本机的 AI 提供商、人工产品资料与目录同步。','Manage local AI settings, product edits and catalog sync.'))+
      `<div class="wb-devtabs" role="tablist">${nav.map(([id,title])=>`<button role="tab" aria-selected="${ui.activeDev===id}" data-wb-action="devtab" ${attr('id',id)}>${esc(title)}</button>`).join('')}</div>`+
      (ui.activeDev==='products'?productsTab():ui.activeDev==='updates'?updateTab():providerForm());
  }

  function paint(){
    if(!app || !customTypes.has(ui.view))return;
    const body=ui.view==='favorites'?favPage():ui.view==='custom'?customPage():developerPage();
    app.view.innerHTML=`<div id="wb-workbench" class="wb-page">${noticeBox()}${body}</div>`;
    app.onContextChange?.();
  }
  function chatContext(view){
    if(view==='developer')return {view,tab:ui.activeDev};
    if(view==='favorites'){
      const saved=favorites();
      return {view,total:saved.length,visibleSkus:saved.slice(0,12),selectedSkus:[...ui.selectedFavorites].filter(s=>saved.includes(s)).slice(0,8),projectId:ui.targetProject||''};
    }
    if(view!=='custom')return {view};
    const list=filteredEligible(),start=(ui.customPage-1)*pageSize,d=ui.projectDraft;
    const context={view,sku:ui.filterSku||'',tab:d?'project':'projects',query:ui.customFilter,page:ui.customPage,total:list.length,visibleSkus:list.slice(start,start+12).map(p=>p.sku)};
    if(d){
      context.projectId=d.id;
      context.projectDraft={title:d.title.slice(0,180),description:d.description.slice(0,1000),labels:splitList(d.labels).slice(0,8),skus:d.skus.slice(0,8)};
      context.selectedSkus=context.projectDraft.skus;
    }else{
      context.projectIds=projects().filter(p=>!ui.filterSku||p.skus.includes(ui.filterSku)).slice(0,6).map(p=>p.id);
    }
    return context;
  }
  function openSettings(){
    ui.activeDev='settings';
    changeView('developer');
  }
  function render(id) {
    if(!customTypes.has(id))return;
    if(ui.view!==id){ui.notice='';ui.noticeError=false;}
    ui.view=id;paint();sidebarFavorites();
    if(id==='developer' && ui.activeDev==='updates' && !ui.update)void pollUpdate();
  }
  async function write(path,body,full=false){
    await app.api(path,{method:'POST',body});
    await app.reloadData(full);
    sidebarFavorites();
  }
  function redraw(){if(active())paint();}
  const disabledDuring=new Set();
  async function task(key,buttonEl,work) {
    if(ui.busy.has(key))return;
    ui.busy.add(key);
    if(buttonEl && !buttonEl.disabled) {disabledDuring.add(buttonEl);buttonEl.disabled=true;}
    try{await work();}catch(e){notify(errorText(e),true);}
    finally{
      ui.busy.delete(key);
      if(buttonEl && disabledDuring.delete(buttonEl))buttonEl.disabled=false;
    }
  }
  async function saveProject(){
    const d=ui.projectDraft;
    if(!d?.skus.length){notify(L('请先添加可定制产品。','Add at least one eligible product.'),true);return;}
    const payload={title:d.title.trim(),description:d.description.trim(),labels:splitList(d.labels),skus:d.skus};
    if(!payload.title){document.getElementById('wb-project-title')?.focus();return;}
    if(d.id)payload.id=d.id;
    await write('/api/project',payload);
    ui.projectDraft=null;redraw();notify(L('定制需求已保存。','Project saved.'));
  }
  async function addFavorites(){
    const members=[...ui.selectedFavorites];
    if(!members.length)return;
    const existing=projects().find(p=>p.id===ui.targetProject);
    ui.filterSku='';
    if(existing){
      editProject(existing.id);
      ui.projectDraft.skus=uniq([...ui.projectDraft.skus,...members]);
    }else ui.projectDraft=newDraft(members);
    changeView('custom');
    document.getElementById('wb-project-form')?.scrollIntoView({block:'start'});
  }
  function setEditor(p=null) {
    ui.editor=defaultEditor(p);
    ui.imageSearch='';
    ui.activeDev='products';
    if(ui.view!=='developer')changeView('developer');else redraw();
    document.getElementById('wb-sku-form')?.scrollIntoView({block:'start'});
  }
  function setDraft(skus){
    ui.projectDraft=newDraft(skus);
    if(ui.view!=='custom')changeView('custom');else redraw();
    document.getElementById('wb-project-title')?.focus();
  }
  let pendingImage=null;
  async function saveProduct(){
    if(pendingImage)await pendingImage;
    const d=ui.editor;if(!d)return;
    const old=d.original;
    const payload={sku:d.sku.trim(),create:d.create};
    const original=defaultEditor(old);
    if(d.create&&getProduct(payload.sku)){notify(L('此 SKU 已存在，请编辑现有产品。','This SKU already exists. Edit the existing product.'),true);return;}
    const fields=['name','summary','url','custom'];
    for(const k of fields){
      const value=d[k].trim();
      if((d.create&&value)||value!==String(original[k]||'').trim())payload[k]=value;
    }
    const value=d.price.trim()===''?null:Number(d.price);
    if(value!==null&&(!Number.isFinite(value)||value<0)){notify(L('价格需为非负数字。','Enter a nonnegative price.'),true);return;}
    if(d.create?value!==null:d.price!==original.price)payload.price=value;
    if(d.create||d.currency.toUpperCase()!==original.currency)payload.currency=d.currency.toUpperCase().trim();
    if(d.manual!==original.manual||d.create&&d.manual)payload.customConfirmed=d.manual;
    if(d.imageData)payload.image=d.imageData;
    else if(d.imageInput.trim()!==original.imageInput)payload.image=d.imageInput.trim();
    if(!d.create&&Object.keys(payload).length===2){notify(L('资料没有变化。','There are no changes to save.'));return;}
    await write('/api/product',payload);
    const product=getProduct(payload.sku);
    ui.editor=product?defaultEditor(product):null;
    redraw();notify(L('产品资料已保存。','Product record saved.'));
  }
  async function readImage(file){
    if(!file || !ui.editor)return;
    if(file.size>12*1024*1024 || !['image/jpeg','image/png','image/webp'].includes(file.type)){
      notify(L('请选择 12 MB 以内的 JPG、PNG 或 WebP。','Choose a JPEG, PNG or WebP under 12 MB.'),true);return;
    }
    const editor=ui.editor;
    const bitmap=await createImageBitmap(file);
    try{
      if(!bitmap.width||!bitmap.height)throw Error('IMAGE_INVALID');
      const ratio=Math.min(1,1000/Math.max(bitmap.width,bitmap.height));
      const canvas=document.createElement('canvas');
      canvas.width=Math.max(1,Math.round(bitmap.width*ratio));canvas.height=Math.max(1,Math.round(bitmap.height*ratio));
      const ctx=canvas.getContext('2d');
      ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);
      ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);
      if(editor!==ui.editor)return;
      editor.imageData=canvas.toDataURL('image/jpeg',0.83);
      const preview=document.getElementById('wb-image-preview');
      if(preview){const img=new Image();img.alt=L('主图预览','Product image preview');img.src=editor.imageData;preview.replaceChildren(img);}
    }finally{bitmap.close();}
  }
  async function saveProvider(clear=false){
    const provider=ui.provider||store().provider||'deepseek', key=document.getElementById('wb-key');
    const model=document.getElementById('wb-model')?.value.trim();
    const payload={provider};
    if(model)payload.model=model;
    if(clear)payload.clearKey=true;
    else if(key?.value.trim())payload.apiKey=key.value.trim();
    if(key)key.value='';
    await write('/api/settings',payload);ui.provider=provider;redraw();
    notify(clear?L('密钥已移除。','API key removed.'):L('AI 设置已保存。','AI settings saved.'));
  }
  function inUpdates(){return active()&&ui.view==='developer'&&ui.activeDev==='updates';}
  function schedulePoll(){
    clearTimeout(ui.updateTimer);
    if(ui.update?.status==='running')ui.updateTimer=setTimeout(()=>void pollUpdate(),1100);
  }
  async function pollUpdate(){
    if(ui.busy.has('poll'))return;
    ui.busy.add('poll');
    try{
      const previous=ui.update;
      ui.update=await app.api('/api/update');
      if(ui.update.status==='done' && ['apply','refresh'].includes(ui.update.action) &&
        previous && (previous.status!=='done'||previous.updatedAt!==ui.update.updatedAt)){
        await app.reloadData(true);sidebarFavorites();
      }
      if(inUpdates()){
        if(previous?.status===ui.update.status && ui.update.status==='running'){
          const area=document.getElementById('wb-job-status');if(area)area.innerHTML=updateStatus();
        }else paint();
      }
      schedulePoll();
    }catch(e){if(inUpdates())notify(errorText(e),true);}
    finally{ui.busy.delete('poll');}
  }
  async function startJob(action,extra={}){
    if(ui.update?.status==='running')return;
    clearTimeout(ui.updateTimer);
    if(action==='preview'){ui.changes.clear();ui.diffPage=1;}
    const previous=ui.update;
    ui.update=await app.api('/api/update',{method:'POST',body:{action,...extra}});
    if(action==='apply'||action==='refresh')ui.changes.clear();
    if(ui.update.status==='done'&&['apply','refresh'].includes(ui.update.action)&&
      (!previous||previous.status!=='done'||previous.updatedAt!==ui.update.updatedAt))await app.reloadData(true);
    if(inUpdates())paint();
    schedulePoll();
  }
  function updateDom(id,content) {
    const el=document.getElementById(id);if(el)el.innerHTML=content;
    if(id==='wb-eligible-list')app.onContextChange?.();
  }
  async function handleClick(b) {
    const action=b.dataset.wbAction,sku=b.dataset.wbSku,id=b.dataset.wbId;
    switch(action){
      case 'open':app.openProduct(sku);break;
      case 'catalog':changeView('catalog');break;
      case 'favorites':changeView('favorites');break;
      case 'star':{
        const saved=favorites().includes(sku);
        await write('/api/favorite',{sku,active:!saved});
        ui.selectedFavorites.delete(sku);redraw();break;
      }
      case 'custom-for':openCustomFor(sku);break;
      case 'favorites-project':await addFavorites();break;
      case 'new-from-sku':setDraft([sku]);break;
      case 'new-project':setDraft(ui.filterSku&&eligible(getProduct(ui.filterSku))?[ui.filterSku]:[]);break;
      case 'edit-project':editProject(id);redraw();document.getElementById('wb-project-title')?.focus();break;
      case 'delete-project':{
        const p=projects().find(it=>it.id===id);
        if(!p||!window.confirm(L('删除定制需求“','Delete project “')+p.title+'”?'))return;
        await write('/api/project',{id,delete:true});
        if(ui.projectDraft?.id===id)ui.projectDraft=null;
        redraw();notify(L('定制需求已删除。','Project deleted.'));break;
      }
      case 'cancel-project':ui.projectDraft=null;redraw();break;
      case 'clear-custom':ui.filterSku='';ui.customPage=1;redraw();break;
      case 'member-add':if(ui.projectDraft&&eligible(getProduct(sku))){ui.projectDraft.skus=uniq([...ui.projectDraft.skus,sku]);redraw();}break;
      case 'member-remove':if(ui.projectDraft){ui.projectDraft.skus=ui.projectDraft.skus.filter(s=>s!==sku);redraw();}break;
      case 'custom-prev':ui.customPage--;updateDom('wb-eligible-list',eligibleList());break;
      case 'custom-next':ui.customPage++;updateDom('wb-eligible-list',eligibleList());break;
      case 'devtab':ui.activeDev=id;ui.notice='';redraw();if(id==='updates')await pollUpdate();break;
      case 'clear-key':if(window.confirm(L('移除此提供商在本机保存的密钥？','Remove the key saved for this provider?')))await saveProvider(true);break;
      case 'edit-sku':setEditor(getProduct(sku));break;
      case 'new-sku':setEditor();break;
      case 'use-image':{
        const from=getProduct(sku);
        if(ui.editor && from){
          ui.editor.imageInput=from.image||from.imageUrl||'';ui.editor.imageData='';ui.imageSearch='';
          redraw();document.getElementById('wb-image-input')?.focus();
        }
        break;
      }
      case 'cancel-editor':ui.editor=null;redraw();break;
      case 'preview-job':await startJob('preview');break;
      case 'apply-job':await startJob('apply',{skus:[...ui.changes]});break;
      case 'refresh-all':await startJob('refresh');break;
      case 'refresh-subset':{
        const skus=splitList(ui.refreshSkus),categories=ui.refreshCategory?[ui.refreshCategory]:[];
        if(!skus.length&&!categories.length){notify(L('请填写 SKU 或选择分类。','Enter at least one SKU or select a category.'),true);return;}
        await startJob('refresh',{skus,categories});break;
      }
      case 'resume-job':await startJob('resume');break;
      case 'diff-prev':ui.diffPage--;updateDom('wb-diff-list',diffRows());break;
      case 'diff-next':ui.diffPage++;updateDom('wb-diff-list',diffRows());break;
    }
  }
  function onInput(e){
    const el=e.target, id=el.id, val=el.value;
    if(el.dataset.wbDraft && ui.projectDraft){
      ui.projectDraft[el.dataset.wbDraft]=val;
      if(el.dataset.wbDraft==='title'||el.dataset.wbDraft==='labels')app.onContextChange?.();
      if(el.dataset.wbDraft==='picker')updateDom('wb-member-options',projectChoices());return;
    }
    if(el.dataset.wbEditor && ui.editor){
      ui.editor[el.dataset.wbEditor]=val;
      if(el.dataset.wbEditor==='imageInput'){
        ui.editor.imageData='';
        const thumb=imageUrl(val);updateDom('wb-image-preview',thumb?`<img src="${esc(thumb)}" alt="">`:'');
      }
      return;
    }
    switch(id){
      case 'wb-custom-filter':ui.customFilter=val;ui.customPage=1;updateDom('wb-eligible-list',eligibleList());break;
      case 'wb-edit-query':ui.editorQuery=val;updateDom('wb-edit-results',editorMatches());break;
      case 'wb-image-search':ui.imageSearch=val;updateDom('wb-image-results',imageMatches());break;
      case 'wb-refresh-skus':ui.refreshSkus=val;break;
      case 'wb-diff-query':ui.diffQuery=val;ui.diffPage=1;updateDom('wb-diff-list',diffRows());break;
    }
  }
  async function onChange(el) {
    if(el.dataset.wbFavCheck){
      if(el.checked)ui.selectedFavorites.add(el.dataset.wbFavCheck);else ui.selectedFavorites.delete(el.dataset.wbFavCheck);redraw();return;
    }
    if(el.dataset.wbDiffsku){
      if(el.checked)ui.changes.add(el.dataset.wbDiffsku);else ui.changes.delete(el.dataset.wbDiffsku);updateDom('wb-diff-list',diffRows());return;
    }
    switch(el.id){
      case 'wb-allfav':ui.selectedFavorites=new Set(el.checked?favorites().filter(s=>eligible(getProduct(s))):[]);redraw();break;
      case 'wb-target-project':ui.targetProject=el.value;app.onContextChange?.();break;
      case 'wb-provider':ui.provider=el.value;redraw();break;
      case 'wb-language':{
        const lang=el.value==='en'?'en':'zh-CN';
        await app.api('/api/settings',{method:'POST',body:{language:lang==='en'?'en':'zh'}});
        await app.onLanguage(lang);
        await app.reloadData();sidebarFavorites();redraw();break;
      }
      case 'wb-manual':if(ui.editor)ui.editor.manual=el.checked;break;
      case 'wb-image-file':
        if(el.files[0]){
          const reading=readImage(el.files[0]);pendingImage=reading;
          try{await reading;}finally{if(reading===pendingImage)pendingImage=null;}
        }
        break;
      case 'wb-refresh-category':ui.refreshCategory=el.value;break;
      case 'wb-select-diff':{
        const shown=changes().filter(c=>c.kind!=='missing'&&(!ui.diffQuery||(c.sku+' '+(c.name||'')).toLowerCase().includes(ui.diffQuery.toLowerCase())));
        for(const item of shown){if(el.checked)ui.changes.add(item.sku);else ui.changes.delete(item.sku);}
        updateDom('wb-diff-list',diffRows());break;
      }
    }
  }
  let initialized=false;
  function init(config){
    app=config;sidebarFavorites();
    if(initialized)return;
    initialized=true;
    document.addEventListener('click',e=>{
      if(e.target.closest('#wb-fav-toggle')){
        favoriteExpanded=!favoritesOpen();
        try{localStorage.setItem(favoritePreference,String(favoriteExpanded));}catch{}
        sidebarFavorites();document.getElementById('wb-fav-toggle')?.focus();return;
      }
      const b=e.target.closest('[data-wb-action]');
      if(!b)return;e.preventDefault();
      void task(b.dataset.wbAction+':'+(b.dataset.wbSku||b.dataset.wbId||''),b,()=>handleClick(b));
    });
    document.addEventListener('input',onInput);
    document.addEventListener('change',e=>{
      const el=e.target;
      if(!el.id?.startsWith('wb-')&&!el.dataset.wbFavCheck&&!el.dataset.wbDiffsku)return;
      void task('change:'+(el.id||el.dataset.wbFavCheck||el.dataset.wbDiffsku),null,()=>onChange(el));
    });
    document.addEventListener('submit',e=>{
      const functions={'wb-project-form':saveProject,'wb-sku-form':saveProduct,'wb-provider-form':()=>saveProvider()};
      const handler=functions[e.target.id];if(!handler)return;
      e.preventDefault();
      void task('submit:'+e.target.id,e.submitter,handler);
    });
  }
  window.Workbench={init,render,sidebarFavorites,productActions,openCustomFor,openProject,openSettings,chatContext,isEligible:eligible,customizationInfo:customInfo};
})();
