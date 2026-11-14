/* Internal documents are read only from the local service and kept in this page's memory. */
(() => {
  'use strict';
  let app, payload=null, loading=null, importedVersion='', query='', page=1, pathDraft=null, busy=false;
  let message='', failed=false, dialog, sourceSerial=0, assessmentTimer, assessmentSerial=0;
  let assessmentKey='', assessmentValue=null, assessmentController;
  const pageSize=20;
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tr=(zh,en,lang=app?.language())=>lang==='en'?en:zh;
  const validId=id=>/^[a-f0-9]{24}$/.test(id||'');
  const status=()=>app?.getState().internalSummary||{};
  const shortVersion=value=>String(value||'').slice(0,12);
  const label=(p,text,lang,badge=true)=>p?.internal?.eol
    ?`<span class="internal-eol-text">${esc(text)}</span>${badge?` <span class="internal-eol-badge">${tr('内部 EOL','Internal EOL',lang)}</span>`:''}`:esc(text);
  const kindName=(kind,lang)=>({eol:tr('生命周期','Lifecycle',lang),ssd:tr('SSD / 存储','SSD / storage',lang),wireless:tr('无线配置','Wireless configuration',lang),logo:tr('Logo / 标识','Logo / marking',lang),customization:tr('定制流程','Customization process',lang),reference:tr('参考资料','Reference',lang),identity:tr('货号与名称','SKU and name',lang)})[kind]||kind;
  function storeLink(url){
    try{
      const parsed=new URL(url);
      if(parsed.protocol==='https:'&&parsed.hostname==='www.seeedstudio.com'&&!parsed.username&&!parsed.password)return `<a class="internal-source" href="${esc(parsed.href)}" target="_blank" rel="noopener noreferrer">${tr('商城商品页','Store product page')} ↗</a>`;
    }catch{}
    return '';
  }
  function sourceButton(record,lang){
    const title=record.sourceTitle||record.title||tr('查看原文','View source',lang);
    return validId(record.sourceId)?`<button type="button" class="internal-source" data-internal-source="${record.sourceId}" data-internal-location="${esc(record.location)}" data-internal-version="${esc(record.version)}">${esc(title)}${record.location?' · '+esc(record.location):''} ↗</button>`:'';
  }
  function provenance(record,lang){
    return `<div class="internal-provenance">${sourceButton(record,lang)}${record.version?`<span title="${esc(record.version)}">${tr('版本','Version',lang)} ${esc(shortVersion(record.version))}</span>`:''}${record.date?`<span>${esc(record.date)}</span>`:''}</div>`;
  }
  function recordCard(record,lang){
    return `<article class="internal-record"><div class="internal-record-heading"><b>${esc(record.title)}</b><span>${esc(kindName(record.kind,lang))}</span></div>${recordBody(record)}${provenance(record,lang)}</article>`;
  }
  function recordBody(record){
    return record.fields?.length?`<dl class="internal-fields">${record.fields.map(field=>`<div><dt>${esc(field.name)}</dt><dd>${esc(field.value)}</dd></div>`).join('')}</dl>`:`<div class="internal-record-text">${esc(record.text)}</div>`;
  }
  function product(p,lang,kind='all'){
    if(!p?.internal?.records?.length)return '';
    const records=p.internal.records.filter(row=>kind==='summary'?row.kind==='eol':kind==='specs'?row.kind==='ssd':kind==='options'?['ssd','wireless','logo','customization'].includes(row.kind):true);
    if(!records.length)return '';
    if(kind==='summary')return `<aside class="internal-eol-notice"><b>${tr('内部资料标记 EOL','Internal EOL notice',lang)}</b><p>${tr('报价前请确认剩余库存与本次项目的使用安排。','Confirm remaining stock and the intended use before quoting.',lang)}</p>${records.map(r=>recordBody(r)+provenance(r,lang)).join('')}</aside>`;
    return `<section class="internal-product-records"><h3>${tr('内部资料','Internal documents',lang)}</h3>${p.internalOnly||p.isInternal?`<p class="caption">${tr('此记录来自本机导入资料，商城商品身份尚未确认。','This record comes from locally imported documents. Its store identity is unconfirmed.',lang)}</p>`:''}${records.map(r=>recordCard(r,lang)).join('')}</section>`;
  }
  function errorText(error){
    const code=String(error?.code||error?.message||error||'');
    const known={FILE_TOO_LARGE:['文件超过允许大小。','The file exceeds the size limit.'],PARSE_FAILED:['文件内容解析失败。','The file could not be parsed.'],INTERNAL_REFRESH_FAILED:['刷新失败，请检查目录和文件内容后重试。','Refresh failed. Check the folder and files, then retry.'],INTERNAL_IMPORT_FAILED:['导入失败，请检查文件格式与访问权限。','Import failed. Check file formats and access permissions.'],INTERNAL_NO_SUPPORTED_FILES:['目录中没有可读取的内部资料文件。','The folder contains no supported internal document files.'],INTERNAL_TOO_MANY_FILES:['目录中的文件数量超过读取上限，请选择更具体的资料目录。','The folder contains too many files. Select a more specific document folder.']};
    if(known[code])return tr(...known[code]);
    if(/ROOT|PATH|DIRECTORY|NOT_FOUND/i.test(code))return tr('无法读取这个目录或来源，请检查路径和访问权限。','The folder or source could not be read. Check the path and access permissions.');
    if(/INVALID|FORMAT|FILE|PARSE/i.test(code))return tr('部分文件无法解析，请查看下方失败记录。','Some files could not be parsed. Check the failures below.');
    return tr('内部资料读取未完成，请检查本地服务后重试。','Internal documents could not be loaded. Check the local service and retry.');
  }
  function summaryMarkup(summary){
    const pairs=[[tr('文件','Files'),summary.documents],[tr('知识条目','Records'),summary.records],[tr('已关联商城 SKU','Matched store SKUs'),summary.matched],[tr('仅内部 SKU','Internal-only SKUs'),summary.unmatched],[tr('内部 EOL','Internal EOL'),summary.eol]];
    return `<div class="internal-stats">${pairs.map(([name,value])=>`<span>${esc(name)} <b>${Number(value||0).toLocaleString()}</b></span>`).join('')}</div>`+
      `${summary.importedAt?`<p class="caption">${tr('上次读取','Last read')} ${esc(new Date(summary.importedAt).toLocaleString(app.language()))} · ${tr('版本','Version')} <span title="${esc(summary.version)}">${esc(shortVersion(summary.version))}</span></p>`:''}`;
  }
  function pane(){
    return '<div id="internal-panel" class="internal-pane" aria-live="polite"></div>';
  }
  function render(){
    const host=document.getElementById('internal-panel');if(!host||!app)return;
    const summary=payload?.summary||status();
    if(pathDraft===null)pathDraft=summary.sourceRoot||'';
    host.innerHTML=`<section class="panel wb-panel"><h2>${tr('本机内部资料','Local internal documents')}</h2><p>${tr('导入内部说明、流程和产品生命周期资料。刷新工作台时会检查已选目录的文件变化。','Import internal guidance, processes and product lifecycle records. Refreshing the workbench checks the selected folder for changes.')}</p>
      <form id="internal-import" class="internal-import"><label class="wb-field"><span>${tr('资料文件夹路径','Document folder path')}</span><input id="internal-path" required autocomplete="off" value="${esc(pathDraft)}" placeholder="${tr('粘贴本机资料目录的完整路径','Paste the full local folder path')}" ${busy?'disabled':''}></label><button class="wb-button wb-primary" type="submit" ${busy?'disabled':''}>${busy?tr('正在读取…','Reading…'):tr('导入 / 重新读取','Import / reread')}</button></form>
      <p class="caption">${tr('内部资料保存在本机。向 AI 发送问题时，相关选中资料会随问题提交给已配置的提供商。','Internal documents are stored locally. When you send an AI question, relevant selected records accompany it to the configured provider.')}</p>
      ${summaryMarkup(summary)}${message?`<p class="${failed?'internal-error':'internal-status'}" role="status">${esc(message)}</p>`:''}
      ${summary.error?`<p class="internal-error">${esc(errorText(summary.error))}</p>`:''}
      ${(summary.errors||[]).length?`<details class="internal-errors" open><summary>${tr('未能解析的文件','Files that could not be parsed')} · ${summary.errors.length}</summary><ul>${summary.errors.map(e=>`<li><b>${esc(e.file)}</b> ${esc(errorText(e.error))}</li>`).join('')}</ul></details>`:''}</section>
      <section class="panel wb-panel"><div class="wb-heading"><h2>${tr('检索内部知识与流程','Search internal knowledge and processes')}</h2><button type="button" class="wb-button" data-internal-action="refresh" ${loading||busy?'disabled':''}>${tr('检查文件变化','Check for file changes')}</button></div><label class="wb-field"><span>${tr('SKU、名称、规则或原文关键词','SKU, name, rule or source keyword')}</span><input id="internal-query" value="${esc(query)}" autocomplete="off"></label><div id="internal-results">${resultsMarkup()}</div></section>
      ${payload?.documents?.length?`<section class="panel wb-panel"><h2>${tr('已读来源','Sources read')}</h2><ul class="internal-documents">${payload.documents.map(d=>`<li>${sourceButton({sourceId:d.id,sourceTitle:d.title,version:d.version},app.language())}<small>${tr('版本','Version')} ${esc(shortVersion(d.version))}${d.modifiedAt?' · '+esc(d.modifiedAt):''}</small></li>`).join('')}</ul></section>`:''}`;
  }
  function resultsMarkup(){
    if(!payload)return `<p class="caption">${loading?tr('正在读取内部资料…','Loading internal documents…'):tr('选择上方文件夹后导入资料。','Select a document folder above to import.')}</p>`;
    const match=catalogQueryMatcher(query),found=payload.records.filter(r=>match(r._search));
    const pages=Math.max(1,Math.ceil(found.length/pageSize));page=Math.min(page,pages);
    const docs=new Map(payload.documents.map(d=>[d.id,d]));
    return `<p class="caption">${found.length} ${tr('条记录','records')}</p>`+found.slice((page-1)*pageSize,page*pageSize).map(r=>{
      const links=(r.skus||[]).map(sku=>{const p=app.getProduct(sku);return p?`<button type="button" class="internal-source" data-internal-product="${esc(p.sku)}">${label(p,p.sku+' · '+p.name,app.language())}</button>`:esc(sku);}).join(' ');
      return recordCard({...r,sourceTitle:docs.get(r.sourceId)?.title},app.language())+(links?`<div class="internal-record-products">${links}</div>`:`<p class="internal-record-products caption">${tr('通用流程 / 参考','General process / reference')}</p>`);
    }).join('')+(!found.length?`<p>${tr('没有匹配的内部条目。','No internal records match.')}</p>`:'')+
      (pages>1?`<div class="wb-pager"><button type="button" class="wb-button" data-internal-page="-1" ${page===1?'disabled':''}>${tr('上一页','Previous')}</button><span>${page} / ${pages}</span><button type="button" class="wb-button" data-internal-page="1" ${page===pages?'disabled':''}>${tr('下一页','Next')}</button></div>`:'');
  }
  function accept(value){
    payload=value;importedVersion=value.summary?.version||'';
    for(const r of payload.records||[])r._search=normalizeCatalogText([r.title,r.text,...(r.skus||[]),r.productName,r.location].join(' '));
  }
  async function read(refreshState=false){
    if(loading)return loading;
    loading=(async()=>{
      try{accept(await app.api('/api/internal'));if(refreshState)await app.reloadData();message='';failed=false;}
      catch(e){message=errorText(e);failed=true;}
      finally{loading=null;render();}
    })();
    render();return loading;
  }
  function mount(){
    if(!app||!document.getElementById('internal-panel'))return;
    if(status().version!==importedVersion)payload=null;
    render();if(!payload&&!loading)void read();
  }
  async function importFiles(){
    if(busy)return;
    const path=(document.getElementById('internal-path')?.value||'').trim();if(!path)return;
    pathDraft=path;busy=true;message='';render();
    try{accept(await app.api('/api/internal',{method:'POST',body:{action:'import',path}}));await app.reloadData();message=tr('内部资料已读取。','Internal documents loaded.');failed=false;}
    catch(e){message=errorText(e);failed=true;}
    finally{busy=false;render();}
  }
  function sourceDialog(){
    if(dialog)return dialog;
    dialog=document.createElement('dialog');dialog.className='internal-source-dialog';dialog.id='internal-source-dialog';dialog.setAttribute('aria-labelledby','internal-source-title');document.body.append(dialog);
    dialog.addEventListener('click',e=>{if(e.target.closest('[data-internal-close]'))dialog.close();});
    dialog.addEventListener('close',()=>{if(!dialog.open)sourceSerial++;});
    dialog.addEventListener('keydown',e=>{if(e.key==='Escape')e.stopPropagation();});
    return dialog;
  }
  async function openSource(sourceId,location='',expectedVersion=''){
    if(!app||!validId(sourceId))return;
    const modal=sourceDialog(),serial=++sourceSerial;
    modal.innerHTML=`<div class="internal-source-heading"><h2 id="internal-source-title">${tr('内部资料原文','Internal source')}</h2><button type="button" class="wb-button" data-internal-close>${tr('关闭','Close')}</button></div><div id="internal-source-content"><p>${tr('正在读取…','Loading…')}</p></div>`;
    if(!modal.open)modal.showModal();
    try{
      const source=await app.api('/api/internal/source/'+sourceId);if(serial!==sourceSerial||!modal.open)return;
      document.getElementById('internal-source-title').textContent=source.title;
      const changed=expectedVersion&&source.version!==expectedVersion;
      const range=!changed&&/^L(\d+)(?:[–-]L?(\d+))?/.exec(location),first=range?Number(range[1]):0,last=range?Number(range[2]||range[1]):0;
      const lines=String(source.text||'').split('\n').map(line=>{
        const n=Number(line.match(/^(\d+):/)?.[1]);
        return n&&n>=first&&n<=last?`<mark>${esc(line)}</mark>`:esc(line);
      }).join('\n');
      document.getElementById('internal-source-content').innerHTML=`${changed?`<p class="internal-error">${tr('当前文件已更新，与此条引用记录的版本不同，请重新核对位置和内容。','The current file has changed since this citation. Recheck the location and content.')} ${tr('引用版本','Cited version')} ${esc(shortVersion(expectedVersion))}</p>`:''}<p class="caption">${esc(location)}${location?' · ':''}${tr('版本','Version')} ${esc(source.version)}${source.modifiedAt?' · '+esc(source.modifiedAt):''}</p>${/\.xlsx$/i.test(source.title)?`<p class="caption">${tr('以下为工作表中已提取的货号、名称及生命周期字段。','The following fields were extracted from the workbook for product identifiers, names and lifecycle status.')}</p>`:''}<pre>${lines}</pre>`;
      modal.querySelector('mark')?.scrollIntoView({block:'center'});
    }catch(e){if(serial===sourceSerial)document.getElementById('internal-source-content').textContent=errorText(e);}
  }
  function assessmentMarkup(result){
    if(!result?.assessments?.length)return `<p>${tr('已选 SKU 暂无可用的内部 SSD 规则，请核对准确型号资料。','No internal SSD rule is available for the selected SKUs. Check the exact model documentation.')}</p>`;
    return `<h3>${tr('SSD 需求核对','SSD requirement review')}</h3><p class="caption">${tr('依据本机内部资料自动核对，可继续编辑和保存需求。','Checked against local internal documents. You can continue editing and save the project.')}</p>`+result.assessments.map(a=>`<article class="internal-assessment"><b>${label(app.getProduct(a.sku),a.sku+' · '+a.name,app.language())}</b>
      ${(a.actions||[]).length?`<ul>${a.actions.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
      ${(a.confirmations||[]).length?`<div class="internal-confirmations"><b>${tr('需要确认','To confirm')}</b><ul>${a.confirmations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:''}
      ${a.replacementSku?`<button class="internal-source" type="button" data-internal-product="${esc(a.replacementSku)}">${esc(a.replacementSku)}</button>`:''}${a.replacementNote?`<p>${esc(a.replacementNote)}</p>`:''}
      ${(a.candidates||[]).length?`<h4>${tr('匹配的 SSD 物料','Matching SSD items')}</h4><ul class="internal-candidates">${a.candidates.map(c=>`<li><b>${esc(c.sku)} · ${esc(c.name)}</b><p class="caption">${esc([c.size,c.capacity,c.grade==='industrial'?tr('工业级','Industrial grade'):c.grade==='commercial'?tr('商业级','Commercial grade'):tr('等级待核','Grade unconfirmed')].filter(Boolean).join(' · '))}</p>${storeLink(c.url)}<div class="internal-candidate-actions"><button type="button" class="wb-button" data-internal-material="${esc(c.sku)}" data-internal-host="${esc(a.sku)}" data-internal-operation="replace">${tr('用此物料替换','Use this item to replace')}</button><button type="button" class="wb-button" data-internal-material="${esc(c.sku)}" data-internal-host="${esc(a.sku)}" data-internal-operation="add">${tr('新增此物料','Add this item')}</button></div>${provenance(c,app.language())}</li>`).join('')}</ul>`:''}
      ${(a.records||[]).map(r=>provenance(r,app.language())).join('')}</article>`).join('');
  }
  function project(skus,description,materials=[]){
    clearTimeout(assessmentTimer);
    const host=document.getElementById('internal-project-review');if(!app||!host)return;
    const key=JSON.stringify([skus,description,materials,app.language(),status().version]);
    if(key===assessmentKey&&assessmentValue){host.innerHTML=assessmentMarkup(assessmentValue);host.hidden=!host.innerHTML;return;}
    assessmentKey=key;assessmentValue=null;++assessmentSerial;assessmentController?.abort();
    if(!skus.length||!/SSD|NVMe|SATA|固态|系统盘|数据盘|存储|storage|system drive|data drive|盘\s*[12一二]|drive\s*[12]/i.test(description)){host.innerHTML='';host.hidden=true;return;}
    const serial=assessmentSerial;host.hidden=false;host.textContent=tr('正在核对 SSD 需求…','Checking SSD requirements…');
    assessmentTimer=setTimeout(async()=>{
      assessmentController=new AbortController();
      try{
        const result=await app.api('/api/internal/assess',{method:'POST',body:{skus:[...skus],description,materials,language:app.language()==='en'?'en':'zh'},signal:assessmentController.signal});
        if(serial!==assessmentSerial)return;
        assessmentValue=result;
        const current=document.getElementById('internal-project-review');if(current){current.innerHTML=assessmentMarkup(result);current.hidden=!current.innerHTML;}
      }catch(e){if(serial===assessmentSerial&&e.name!=='AbortError'){const current=document.getElementById('internal-project-review');if(current)current.textContent=errorText(e);}}
    },280);
  }
  function init(config){
    if(app)return;app=config;
    document.addEventListener('click',e=>{
      const source=e.target.closest('[data-internal-source]');if(source){e.preventDefault();void openSource(source.dataset.internalSource,source.dataset.internalLocation||'',source.dataset.internalVersion||'');return;}
      const material=e.target.closest('[data-internal-material]');
      if(material){
        const {internalMaterial:sku,internalHost:hostSku,internalOperation:action}=material.dataset;
        const host=assessmentValue?.assessments.find(a=>a.sku===hostSku);
        if(host?.candidates?.some(c=>c.sku===sku)&&['add','replace'].includes(action))window.Workbench?.addMaterial({sku,hostSku,action});
        return;
      }
      const product=e.target.closest('[data-internal-product]');if(product){app.openProduct(product.dataset.internalProduct);return;}
      const paging=e.target.closest('[data-internal-page]');if(paging){page+=Number(paging.dataset.internalPage);document.getElementById('internal-results').innerHTML=resultsMarkup();return;}
      if(e.target.closest('[data-internal-action="refresh"]'))void read(true);
    });
    document.addEventListener('input',e=>{
      if(e.target.id==='internal-path')pathDraft=e.target.value;
      if(e.target.id==='internal-query'){query=e.target.value;page=1;document.getElementById('internal-results').innerHTML=resultsMarkup();}
    });
    document.addEventListener('submit',e=>{if(e.target.id==='internal-import'){e.preventDefault();void importFiles();}});
  }
  window.InternalUI={init,pane,mount,product,label,sourceButton,openSource,project};
})();
