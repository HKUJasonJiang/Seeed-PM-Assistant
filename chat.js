(() => {
  'use strict';

  let app, root, ui, active = '', list = [], connected = false;
  let epoch = 0, selection = 0, loading = '', listError = '', loadError = '', creating = false;
  let historyVisible = false, opened = false, hasSelection = false, inputComposing = false;
  let recovery = null, recoveryTimer = 0;
  const chats = new Map(), drafts = new Map(), attempts = new Map();
  const storageKey = 'seeed.workbench.chat.v1';
  const l = (zh,en) => app.language() === 'en' ? en : zh;
  const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icon = (path,size=18) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;
  const marks = {
    bubble:icon('<path d="M20 11a8 8 0 0 1-8 8H8l-5 3 1.2-5A8.6 8.6 0 0 1 3 12a8.5 8.5 0 0 1 17-1Z"/><path d="M7.8 11.8h.1m3.6 0h.1m3.6 0h.1" stroke-width="2.8"/>',25),
    history:icon('<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16m3-11h5m-5 4h4"/>'),
    add:icon('<path d="M12 5v14M5 12h14"/>'), close:icon('<path d="m6 6 12 12m0-12L6 18"/>'),
    send:icon('<path d="M12 20V4m-6.5 6.5L12 4l6.5 6.5"/>'), context:icon('<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 2v3m10 7h-3m-7 10v-3M2 12h3"/>',15)
  };
  const field = name => root.querySelector('[data-chat-node="'+name+'"]');
  const tag = (node,value) => { node.textContent = value; };
  const label = (node,value) => { node.setAttribute('aria-label',value);node.title=value; };
  const hot = () => Boolean(app.profile()?.providers?.[app.profile()?.provider || 'deepseek']?.hasKey);
  const vendor = () => app.profile()?.provider === 'doubao' ? l('豆包','Doubao') : 'DeepSeek';
  const current = () => app.getContext?.() || {};
  const viewNames = () => ({
    assistant:l('选型工作台','Product selection'), catalog:l('产品目录','Catalogue'),
    favorites:l('收藏','Favourites'),custom:l('定制服务','Customization'),
    coverage:l('资料覆盖','Coverage'),developer:l('开发者设置','Developer settings')
  });
  const tabNames = () => ({
    attributes:l('技术规格','Specifications'),parts:l('随箱清单','In the box'),accessories:l('配件与定制','Accessories & customization'),
    docs:l('官方文档','Documents'),notes:l('配件与定制','Accessories & customization'),specs:l('技术规格','Specifications')
  });
  const formatTime = stamp => {
    if(!stamp || !Number.isFinite(Date.parse(stamp)))return '';
    return new Intl.DateTimeFormat(app.language()==='en'?'en':'zh-CN',
      {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(stamp));
  };
  function savePrefs(){
    try { localStorage.setItem(storageKey,JSON.stringify({active,opened})); } catch {}
  }
  function readPrefs(){
    try {
      const prefs = JSON.parse(localStorage.getItem(storageKey)||'null');
      if(prefs){active=typeof prefs.active==='string'?prefs.active:'';opened=prefs.opened===true;hasSelection=true;}
    } catch {}
    try {
      const record=JSON.parse(sessionStorage.getItem(storageKey+'.request')||'null');
      if(record?.chat && record?.request && record?.until>Date.now())recovery=record;
    } catch {}
  }
  function rememberRequest(record){
    try {
      if(record)sessionStorage.setItem(storageKey+'.request',JSON.stringify(record));
      else sessionStorage.removeItem(storageKey+'.request');
    } catch {}
  }
  function finishRecovery(){
    recovery=null;clearTimeout(recoveryTimer);recoveryTimer=0;rememberRequest(null);
  }
  async function recover(){
    if(!recovery||!opened||!connected||recoveryTimer)return;
    const entry=recovery;
    if(entry.until<=Date.now()){finishRecovery();paint();return;}
    recoveryTimer=setTimeout(async()=>{
      try{
        const {chat}=await app.api('/api/chats/'+encodeURIComponent(entry.chat));
        if(recovery!==entry)return;
        if(chat.turns?.some(t=>t.id===entry.request)){upsert(chat);finishRecovery();paint(active===entry.chat);return;}
      }catch{}
      recoveryTimer=0;
      if(recovery===entry)recover();
    },2500);
  }
  function button(action,text,extra=''){
    return `<button type="button" class="sc-link" data-chat-action="${action}" ${extra}>${esc(text)}</button>`;
  }
  function safeOfficial(raw){
    try {
      const u=new URL(raw);
      if(u.protocol==='https:'&&!u.username&&!u.password)return u.href;
    } catch {}
    return '';
  }
  function sourceRow(s,index){
    const kind=s.kind||'official', id=s.id??(index+1), text=s.title||s.sku||l('资料','Record');
    const fromPage=kind==='context'||kind==='page'||(kind==='local'&&!s.sku);
    const type=fromPage?l('当前工作台页面','Current workbench page'):kind==='local'?l('工作台人工资料','Local product record'):
      kind==='project'?l('定制项目','Project'):l('官方资料','Official source');
    const url=kind==='official'?safeOfficial(s.url):'';
    let content=esc(text);
    if(url)content=`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(text)} ↗</a>`;
    else if(kind==='local'&&s.sku)content=`<a href="#product=${encodeURIComponent(s.sku)}">${esc(text)} ›</a>`;
    else if(kind==='project'&&s.projectId&&app.openProject)content=button('project',text+' ›','data-chat-project="'+esc(s.projectId)+'"');
    return `<li><span class="sc-ref">[${esc(id)}]</span><span><small>${esc(type)}</small> ${content}</span></li>`;
  }
  function contextLine(ctx,sku){
    const names=viewNames(), tabs=tabNames(), main=ctx?.sku||sku;
    const values=[names[ctx?.view],main?'SKU '+main:'',tabs[ctx?.tab]||ctx?.tab,ctx?.category==='*'?'':ctx?.category,ctx?.filter,ctx?.query];
    if(ctx?.view==='custom'&&ctx.projectDraft?.title)values.push(ctx.projectDraft.title);
    return [...new Set(values.filter(Boolean))].join(' · ');
  }
  const codeOf = err => err?.code||err?.message||'';
  function problem(code){
    const words = {
      API_KEY_REQUIRED:['请先在开发者设置保存模型密钥。','Save a model key in developer settings first.'],
      AI_AUTH_FAILED:['模型密钥无效或没有访问权限。','The model key is invalid or lacks access.'],
      AI_QUOTA_OR_BALANCE:['模型账户余额或配额不足。','The provider account has insufficient balance or quota.'],
      AI_RATE_LIMIT:['模型服务限流，请稍后重试。','The provider is rate-limiting requests. Try again later.'],
      AI_MODEL_OR_REQUEST_INVALID:['请核对开发者设置中的模型名称。','Check the model name in developer settings.'],
      AI_CITATIONS_UNVERIFIED:['模型返回的引用未通过核对。','The model returned citations that could not be verified.'],
      AI_REQUEST_RUNNING:['已有消息正在处理。稍后可重试原消息。','A message is already processing. You can retry the original message shortly.'],
      INVALID_AI_RESPONSE:['模型返回的内容无法读取。','The model returned an unreadable response.'],
      AI_PROVIDER_UNAVAILABLE:['暂时无法连接模型服务。','The model provider is temporarily unavailable.'],
      UNKNOWN_CHAT:['找不到这段会话，请刷新会话列表。','Conversation not found. Refresh the history.'],
      CHAT_TURN_LIMIT:['这段会话已满，请新建会话继续。','This conversation is full. Start a new conversation to continue.'],
      CHAT_LIMIT:['本地会话数量已达上限。','The local conversation limit has been reached.']
    };
    return words[code]?l(...words[code]):l('本次操作未完成，请检查本地服务后重试。','This operation could not finish. Check the local service and retry.');
  }
  function init(opts){
    if(root)return;
    app=opts;root=opts.root;
    root.innerHTML=`<button class="sc-orb" type="button" data-chat-action="toggle" aria-controls="seeed-chat-panel" aria-expanded="false">${marks.bubble}</button>
      <section id="seeed-chat-panel" class="sc-panel" role="dialog" aria-modal="false" aria-labelledby="seeed-chat-title" hidden>
        <div class="sc-top"><button class="sc-icon" type="button" data-chat-action="history" aria-controls="seeed-chat-history">${marks.history}</button>
          <div class="sc-heading"><strong id="seeed-chat-title"></strong><span data-chat-node="title"></span></div>
          <button class="sc-icon" type="button" data-chat-action="new">${marks.add}</button>
          <button class="sc-icon" type="button" data-chat-action="close">${marks.close}</button></div>
        <div class="sc-body"><div class="sc-history" id="seeed-chat-history" hidden><div class="sc-history-head"><strong data-chat-node="historyTitle"></strong>
          <button type="button" class="sc-link" data-chat-action="reload"></button></div><div data-chat-node="sessions"></div></div>
          <div class="sc-main"><div class="sc-context">${marks.context}<div><small data-chat-node="contextTitle"></small><span data-chat-node="context"></span></div>
            <button data-chat-action="evidence" type="button" class="sc-link"></button></div>
            <div class="sc-scroll" data-chat-node="scroll" tabindex="0"><div data-chat-node="turns"></div></div>
            <form class="sc-compose" novalidate><div data-chat-node="notice"></div><div class="sc-entry"><textarea rows="2" maxlength="4000" data-chat-node="input"></textarea>
              <button class="sc-send" type="submit">${marks.send}</button></div>
              <div class="sc-foot"><span data-chat-node="provider"></span><span data-chat-node="shortcut"></span></div></form></div></div>
        <span class="sc-sr" data-chat-node="live" aria-live="polite" aria-atomic="true"></span></section>`;
    ui={};
    for(const n of ['title','historyTitle','contextTitle','context','sessions','scroll','turns','notice','input','provider','shortcut','live'])ui[n]=field(n);
    for(const [n,sel] of Object.entries({panel:'.sc-panel',orb:'.sc-orb',history:'.sc-history',toggleHistory:'[data-chat-action="history"]',
      send:'.sc-send',add:'[data-chat-action="new"]',close:'[data-chat-action="close"]',evidence:'[data-chat-action="evidence"]',
      reload:'[data-chat-action="reload"]',heading:'#seeed-chat-title'}))ui[n]=root.querySelector(sel);
    readPrefs();connected=Boolean(app.connected());
    const wide=window.matchMedia('(min-width: 760px)');
    historyVisible=wide.matches;
    wide.addEventListener('change',e=>{historyVisible=e.matches;paint();});
    root.addEventListener('click',click);
    root.querySelector('form').addEventListener('submit',e=>{e.preventDefault();startSend();});
    ui.input.addEventListener('input',()=>{drafts.set(active,ui.input.value);syncControls();});
    ui.input.addEventListener('compositionstart',()=>{inputComposing=true;});
    ui.input.addEventListener('compositionend',()=>{inputComposing=false;});
    root.addEventListener('keydown',key);
    paint(true);if(opened&&connected){refreshList();recover();}
  }
  function syncControls(){
    const waiting=creating||!!loading||!!loadError||!!recovery||Array.from(attempts.values()).some(a=>a.state==='sending');
    ui.send.disabled=!connected||!hot()||waiting||!ui.input.value.trim();
    const enabled=connected&&hot();
    ui.input.disabled=!enabled||creating;
    ui.add.disabled=creating;
    label(ui.send,waiting?l('正在处理','Processing'):l('发送消息','Send message'));
    ui.input.placeholder=enabled?l('输入问题…','Ask a question…'):l('连接模型后可输入问题','Connect a model to ask a question');
    label(ui.input,l('给 AI 助手的消息','Message the AI assistant'));
    tag(ui.provider,enabled?vendor():'');
    tag(ui.shortcut,l('Enter 发送 · Shift+Enter 换行','Enter to send · Shift+Enter for a new line'));
  }
  function renderNotice(){
    const last=chats.get(active)?.turns?.at(-1), prev=last?.sku, now=current().sku;
    let notice='';
    if(!connected)notice=esc(l('双击项目文件夹里的「启动助手.cmd」，即可使用本地会话与 AI。','Open “启动助手.cmd” in the project folder to use saved conversations and AI.'));
    else if(!hot())notice=esc(l('尚未为 '+vendor()+' 设置密钥。','No key is configured for '+vendor()+'.'))+' '+button('settings',l('设置模型密钥','Set model key'));
    else if(prev && prev!==now)notice=esc(now?l('本轮将使用 SKU '+now+'，上一轮为 '+prev+'。','This message will use SKU '+now+'. The previous message used '+prev+'.'):
      l('已离开 SKU '+prev+'；下一条消息将使用当前页面。','You have left SKU '+prev+'. Your next message will use the current page.'));
    if(ui.notice._markup!==notice){ui.notice.innerHTML=notice;ui.notice._markup=notice;}
    ui.notice.hidden=!notice;
  }
  function sync(){
    if(!root)return;
    const was=connected;connected=Boolean(app.connected());
    paint(false);
    if(opened&&connected&&!was){refreshList();recover();}
  }
  function paint(forceBottom=false){
    ui.orb.setAttribute('aria-expanded',String(opened));ui.panel.hidden=!opened;ui.orb.classList.toggle('sc-active',opened);
    label(ui.orb,opened?l('收起 AI 助手','Close AI assistant'):l('打开 AI 助手','Open AI assistant'));
    label(ui.close,l('收起对话','Close conversation'));label(ui.add,l('新建会话','New conversation'));
    label(ui.toggleHistory,l('会话历史','Conversation history'));ui.toggleHistory.setAttribute('aria-expanded',String(historyVisible));
    ui.history.hidden=!historyVisible;tag(ui.heading,l('AI 助手','AI assistant'));tag(ui.historyTitle,l('会话历史','History'));
    tag(ui.reload,l('刷新','Refresh'));label(ui.reload,l('刷新本地会话记录','Refresh local conversations'));
    const ctxInfo=current();
    const draft=ctxInfo.view==='custom'&&ctxInfo.tab==='project'&&ctxInfo.projectDraft?.description;
    tag(ui.contextTitle,draft?l('发送时附上选中项目资料及当前描述','Sending includes the selected project and its current description'):
      l('发送时附上当前页面选中的资料','Sending includes selection from this page'));
    tag(ui.evidence,l('查看依据','View evidence'));ui.evidence.hidden=!app.openEvidence;
    const ctx=app.getContextLabel?.()||contextLine(current())||l('工作台','Workspace');
    tag(ui.context,ctx);ui.context.title=ctx;
    const meta=chats.get(active)||list.find(c=>c.id===active);
    tag(ui.title,displayTitle(meta));ui.title.title=ui.title.textContent;
    label(ui.scroll,l('对话内容','Conversation messages'));
    renderList();renderTurns(forceBottom);renderNotice();syncControls();
  }
  function displayTitle(c){
    return (c?.turnCount||c?.turns?.length)?c.title||l('会话','Conversation'):l('新会话','New conversation');
  }
  function renderList(){
    let html='';
    if(listError)html=`<p class="sc-error">${esc(problem(listError))}</p>`;
    html+=list.map(c=>`<button class="sc-thread" type="button" data-chat-action="select" data-chat-id="${esc(c.id)}" aria-current="${c.id===active?'true':'false'}">
      <span>${esc(displayTitle(c))}</span><small>${esc(formatTime(c.updatedAt))}</small></button>`).join('');
    if(!list.length&&!listError)html=`<p class="sc-muted">${esc(l('还没有会话','No conversations yet'))}</p>`;
    if(ui.sessions._markup!==html){ui.sessions.innerHTML=html;ui.sessions._markup=html;}
  }
  function userBubble(value,ctx,sku){
    const caption=contextLine(ctx,sku);
    return `<div class="sc-question">${caption?`<div class="sc-turn-context">${esc(caption)}</div>`:''}<div class="sc-bubble">${esc(value)}</div></div>`;
  }
  function renderTurns(forceBottom){
    const atBottom=ui.scroll.scrollHeight-ui.scroll.clientHeight-ui.scroll.scrollTop<65;
    let html='';
    if(loading)html=`<p class="sc-muted sc-blank">${esc(l('正在读取会话…','Loading conversation…'))}</p>`;
    else if(loadError)html=`<p class="sc-error sc-blank">${esc(problem(loadError))} ${button('reload',l('重试','Retry'))}</p>`;
    else{
      for(const turn of chats.get(active)?.turns||[]){
        const sources=turn.sources||[];
        html+=userBubble(turn.query,turn.pageContext,turn.sku)+`<div class="sc-response"><div class="sc-answer">${esc(turn.answer)}</div>
          ${sources.length?`<details class="sc-sources"><summary>${esc(l('引用来源','Sources'))} · ${sources.length}</summary><ul>${sources.map(sourceRow).join('')}</ul></details>`:''}</div>`;
      }
      const attempt=attempts.get(active);
      if(attempt){
        html+=userBubble(attempt.body.query,attempt.body.context,attempt.body.sku);
        html+=attempt.state==='sending'?`<p class="sc-progress"><i></i>${esc(l('正在生成回复…','Generating a reply…'))}</p>`:
          `<div class="sc-failure"><span>${esc(problem(attempt.error))}</span> ${button('retry',l('重试原消息','Retry original message'))}</div>`;
      }
      if(recovery?.chat===active)html+=`<p class="sc-progress"><i></i>${esc(l('正在检查上次已发送的消息…','Checking the previously submitted message…'))}</p>`;
      if(!html)html=`<div class="sc-blank"><span class="sc-motif">${marks.bubble}</span><strong>${esc(l('想了解什么？','What would you like to know?'))}</strong>
        <p>${esc(l('可以问当前产品的配置、选配件，或比较几个候选型号。','Ask about the current product, its accessories, or how candidate models compare.'))}</p></div>`;
    }
    // Keep open references and the reading position when only the surrounding page changes.
    if(ui.turns._markup!==html){ui.turns.innerHTML=html;ui.turns._markup=html;if(atBottom||forceBottom)ui.scroll.scrollTop=ui.scroll.scrollHeight;}
    else if(forceBottom)ui.scroll.scrollTop=ui.scroll.scrollHeight;
  }
  function upsert(chat){
    chats.set(chat.id,chat);
    list=[chat,...list.filter(c=>c.id!==chat.id)].sort((a,b)=>String(b.updatedAt||'').localeCompare(String(a.updatedAt||'')));
  }
  function pick(id){
    active=id;hasSelection=true;++selection;loadError='';loading='';savePrefs();
    ui.input.value=drafts.get(id)||'';paint(true);
  }
  async function readOne(id,token,force){
    if(!id||(!force&&chats.has(id)))return;
    if(active===id&&!chats.has(id)){loading=id;paint();}
    const version=chats.get(id)?.updatedAt;
    try{
      const result=await app.api('/api/chats/'+encodeURIComponent(id));
      if(chats.get(id)?.updatedAt===version)upsert(result.chat);
    }catch(error){if(active===id&&selection===token)loadError=codeOf(error)||'UNAVAILABLE';}
    finally{if(active===id&&selection===token){loading='';paint(true);}}
  }
  async function refreshList(){
    if(!connected)return;
    const request=++epoch, atSelection=selection;
    listError='';
    try{
      const result=await app.api('/api/chats');if(request!==epoch)return;
      list=result.chats||[];
      if(selection===atSelection){
        if(active&&!list.some(c=>c.id===active)||!hasSelection)pick(list[0]?.id||'');
        if(active)await readOne(active,selection,true);
      }
    }catch(error){if(request===epoch)listError=codeOf(error)||'UNAVAILABLE';}
    if(request===epoch)paint();
  }
  function open(){
    if(opened)return;
    opened=true;savePrefs();paint();(ui.input.disabled?ui.close:ui.input).focus();
    if(connected){refreshList();recover();}
  }
  function close(){
    opened=false;savePrefs();paint();ui.orb.focus();
  }
  function click(e){
    const btn=e.target.closest('button[data-chat-action]');if(!btn||!root.contains(btn))return;
    switch(btn.dataset.chatAction){
      case 'toggle':opened?close():open();break;
      case 'close':close();break;
      case 'history':historyVisible=!historyVisible;paint();break;
      case 'reload':refreshList();break;
      case 'new':pick('');if(window.innerWidth<760)historyVisible=false;paint();if(!ui.input.disabled)ui.input.focus();break;
      case 'select':{
        if(window.innerWidth<760)historyVisible=false;
        pick(btn.dataset.chatId);readOne(active,selection,true);break;
      }
      case 'settings':close();app.openSettings?.();break;
      case 'evidence':close();app.openEvidence?.();break;
      case 'project':if(app.openProject?.(btn.dataset.chatProject))close();break;
      case 'retry':{const a=attempts.get(active);if(a?.state==='failed'&&hot()&&connected)deliver(active,a);break;}
    }
  }
  function key(e){
    if(e.key==='Escape'&&opened){e.preventDefault();e.stopPropagation();close();return;}
    if(e.target===ui.input&&e.key==='Enter'&&!e.shiftKey&&!inputComposing&&!e.isComposing&&e.keyCode!==229){
      e.preventDefault();startSend();
    }
  }
  async function startSend(){
    if(ui.send.disabled)return;
    const query=ui.input.value.trim();if(!query)return;
    const ctx=JSON.parse(JSON.stringify(current()));
    const body={requestId:crypto.randomUUID(),query,lang:app.language()==='en'?'en':'zh',sku:ctx.sku||'',
      alternativeSkus:Array.isArray(ctx.alternativeSkus)?ctx.alternativeSkus:[],context:ctx};
    let id=active;
    if(!id){
      creating=true;syncControls();const atSelection=selection;
      try{
        const result=await app.api('/api/chats',{method:'POST',body:{lang:body.lang}});
        id=result.chat.id;upsert(result.chat);
        if(selection===atSelection)pick(id);
        drafts.delete('');
      }catch(error){
        listError=codeOf(error)||'UNAVAILABLE';historyVisible=true;paint();return;
      }finally{creating=false;syncControls();}
    }
    drafts.delete(id);
    if(active===id){ui.input.value='';ui.input.focus();}
    deliver(id,{body});
  }
  async function deliver(id,attempt){
    if(creating||Array.from(attempts.values()).some(a=>a.state==='sending'))return;
    attempt.state='sending';attempt.error='';attempts.set(id,attempt);paint(true);
    rememberRequest({chat:id,request:attempt.body.requestId,until:Date.now()+120000});
    tag(ui.live,l('消息已发送，正在生成回复。','Message sent. Generating a reply.'));
    try{
      const result=await app.api('/api/chats/'+encodeURIComponent(id)+'/send',{method:'POST',body:attempt.body});
      upsert(result.chat);attempts.delete(id);rememberRequest(null);tag(ui.live,l('已收到回复。','Reply received.'));
    }catch(error){
      if(error.status)rememberRequest(null);
      attempt.state='failed';attempt.error=codeOf(error)||'UNAVAILABLE';tag(ui.live,problem(attempt.error));
    }
    paint(active===id);
  }
  window.WorkbenchChat={init,sync,open};
})();
