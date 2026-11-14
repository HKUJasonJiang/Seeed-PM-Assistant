/* Built-in catalogue annotations. Product names, source text and user entries stay as written. */
const builtInProductText={
  '含电源适配器版':'Power adapter included','无电源适配器版':'Without power adapter',
  'Logo、包装、固件烧录（J30/40 系列）':'Logo, packaging and firmware flashing (J30/40 family)',
  'Logo、包装、固件烧录（Super J4012 系列）':'Logo, packaging and firmware flashing (Super family)',
  'Logo、包装、固件烧录（Industrial J4012 系列）':'Logo, packaging and firmware flashing (Industrial family)',
  'Logo、包装、标签、固件烧录（R 系列）':'Logo, packaging, labels and firmware flashing (R family)',
  'M.2 Key E · Wi-Fi 扩展':'M.2 Key E · Wi-Fi expansion','最高 100 TOPS':'Up to 100 TOPS','不支持 Super 模式':'Super mode unsupported',
  '双千兆网口':'Dual Gigabit Ethernet','DIN 导轨安装':'DIN-rail mounting','网卡与天线套件':'Wireless card and antenna kit','网卡单品':'Wireless card only',
  'Wi-Fi / 蓝牙模块':'Wi-Fi / Bluetooth module','交流电源线':'AC power cord','CR1220 电池':'CR1220 battery','电源适配器':'Power adapter','LTE 4G 模块':'LTE 4G module','壁挂支架':'Wall-mount brackets',
  '另购说明':'Sold separately','定制说明':'Customization reference','该 SKU 不含电源适配器。':'This SKU excludes the power adapter.',
  'Part List 注明随附适配器不含交流电源线。':'The part list says the supplied adapter excludes its AC power cord.',
  '壁挂支架需另购。':'Wall-mount brackets are sold separately.','手册印刷第 44 页':'Manual, printed page 44',
  'Wi-Fi 选配套件':'Optional Wi-Fi kit','商品页 Also Add 加购项':'Store suggestion · Also Add','套件内的网卡型号':'Wireless card used in the kit',
  '含网卡与天线，按套件选购。 此主机商品页也列入 Also Add。':'Wireless card and antennas sold as a kit, also listed under Also Add on the host page.',
  '含网卡与天线，按套件选购。':'Wireless card and antennas sold as a kit.'
};
function localizedProductText(value,lang){
  return lang==='en'?(builtInProductText[value]||value||''):(value||'');
}
function mergeProductData(base,overrides,internalProducts={}){
  const patches=new Map(Object.values(overrides||{}).map(p=>[p.sku.toLowerCase(),p]));
  const internal=new Map(Object.entries(internalProducts||{}).map(([sku,p])=>[sku.toLowerCase(),p]));
  const defaults={name:'',url:'',groups:[],paths:[],parts:[],attributes:[],notes:[],docs:[],summary:'',accessories:[],wikiLinks:[],wikiEvidence:[]};
  const products=base.products.map(p=>{
    const key=p.sku.toLowerCase(),patch=patches.get(key);
    const knowledge=internal.get(key);internal.delete(key);
    patches.delete(key);
    if(!patch&&!knowledge)return p;
    return {...p,...patch,...(patch?{isEdited:true}:{}),sku:p.sku,...(knowledge?{internal:knowledge}:{})};
  });
  for(const patch of patches.values()){
    const knowledge=internal.get(patch.sku.toLowerCase());internal.delete(patch.sku.toLowerCase());
    products.push({...defaults,...patch,isEdited:true,isLocal:true,...(knowledge?{internal:knowledge,isInternal:!!knowledge.internalOnly}:{})});
  }
  for(const [sku,knowledge] of internal)products.push({...defaults,sku:knowledge.sku||sku,name:knowledge.name||knowledge.sku||sku,isLocal:true,isInternal:true,internal:knowledge});
  return {...base,products};
}

// Match repeated source rows conservatively. Similar model names or frequencies are separate items.
function accessoryGroups(product,services,resolve){
  const identity=value=>String(value||'').normalize('NFKC').toLowerCase().replace(/[‐‑–—]/g,'-')
    .replace(/wi[ -]?fi/g,'wifi').replace(/\s+/g,' ').replace(/^[\s•]+|[\s.;。；]+$/g,'').trim();
  const groups=new Map(),names=new Map();
  const groupFor=key=>{
    if(!groups.has(key))groups.set(key,{items:[],notes:[],services:[],matches:[],match:null});
    return groups.get(key);
  };
  const aliases=(item,match)=>[item.name,item.storeName,match?.product?.name].map(identity).filter(Boolean);
  const index=(aliases,group)=>{
    for(const alias of aliases){if(!names.has(alias))names.set(alias,new Set());names.get(alias).add(group);}
  };
  const find=aliases=>{
    const found=new Set(aliases.flatMap(alias=>[...(names.get(alias)||[])]));
    return found.size===1?[...found][0]:null;
  };
  const records=(product.accessories||[]).map(item=>({item,match:resolve(item)}));
  const identified=({item,match})=>match?.product?.sku||item.sku||item.publishedSku;
  for(const record of records.filter(identified)){
    const group=groupFor('sku:'+String(identified(record)).toLowerCase());
    group.items.push(record.item);
    if(record.match){group.match=group.match||record.match;group.matches.push(record.match);}
    index(aliases(record.item,record.match),group);
  }
  for(const record of records.filter(r=>!identified(r))){
    const keys=aliases(record.item,null);
    const group=find(keys)||groupFor('name:'+identity(record.item.name));
    group.items.push(record.item);index(keys,group);
  }
  for(const note of product.notes||[]){
    const text=identity(note.text);
    const item=text.replace(/\s+(?:is|are) (?:sold separately|not included)$/,'');
    const group=find([text,item])||groupFor('note:'+text);
    group.notes.push(note);
  }
  for(const service of services.filter(s=>s?.text)){
    const text=identity(service.text);
    const group=find([text])||groups.get('note:'+text)||groupFor('service:'+text);
    group.services.push(service);
  }
  return [...groups.values()];
}

const offerPreferences=new Map();
function offersExpanded(sku){
  if(!offerPreferences.has(sku)){
    let saved=false;
    try{saved=localStorage.getItem('seeed.offerExpanded.'+sku)==='true';}catch{}
    offerPreferences.set(sku,saved);
  }
  return offerPreferences.get(sku);
}
if(typeof document!=='undefined')document.addEventListener('click',event=>{
  const summary=event.target.closest('details[data-offer-sku] > summary');
  if(!summary)return;
  const details=summary.parentElement,sku=details.dataset.offerSku,expanded=!details.open;
  offerPreferences.set(sku,expanded);
  try{localStorage.setItem('seeed.offerExpanded.'+sku,String(expanded));}catch{}
});
