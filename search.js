/* Local deterministic matching. The explicit model stays selected when a requirement conflicts. */
function createSearch(catalog,language='zh-CN',isCustom=p=>Boolean(p.custom&&p.customUrl||p.customConfirmed)) {
  const en=language==='en';
  const pick=(zh,eng)=>en?eng:zh;
  const products = catalog.products;
  const bySku = new Map(products.map(p => [p.sku.toLowerCase(), p]));
  const lower = text => (text || '').toLowerCase().replace(/[‑–—]/g, '-');
  const traits = [
    {key:'super',label:'Super 模式',ask:/super(?:\s*mode|\s*模式)?|maxn|157\s*tops/i,yes:p=>p.series==='super'},
    {key:'wifi',label:'Wi-Fi',ask:/wi[\s-]?fi|无线网|无线局域网/i,word:/wi[\s-]?fi|wireless nic/i},
    {key:'lora',label:'LoRa',ask:/lora|eu868|us915|远距离无线/i,word:/lora|meshtastic/i},
    {key:'ether',label:'双网口',ask:/双网口|双千兆|双以太网|dual\s*(?:gbe|ethernet)/i,word:/dual[- ](?:ethernet|gbe)|2\s*[x×]\s*(?:gigabit|gbe)|双千兆/i},
    {key:'ip66',label:'IP66',ask:/ip66|防水|防尘防水/i,word:/ip66|ip67|ip68/i},
    {key:'rs485',label:'RS485',ask:/rs[ -]?485|工业串口/i,word:/rs[ -]?485/i},
    {key:'custom',label:'定制',ask:/定制|贴牌|印标|logo|刷固件|customi[sz]|branding/i,yes:isCustom},
    {key:'gateway',label:'网关',ask:/网关|gateway/i,word:/gateway/i},
    {key:'jetson',label:'Jetson 边缘计算',ask:/jetson|边缘\s*(?:ai|推理|视觉)|视频分析|边缘计算机/i,word:/jetson/i},
    {key:'pi',label:'树莓派',ask:/树莓派|raspberry\s*pi|\bcm[45]\b/i,word:/raspberry pi|\bcm[45]\b/i},
    {key:'fanless',label:'无风扇',ask:/无风扇|fanless/i,word:/fanless/i},
    {key:'edge',label:'边缘设备',ask:/边缘|edge/i,word:/edge/i},
    {key:'din',label:'DIN 导轨',ask:/导轨|din[ -]?rail/i,word:/din[ -]?rail|din 导轨/i},
    {key:'sensor',label:'传感器',ask:/传感器|sensor/i,word:/sensor/i},
    {key:'temp',label:'温度',ask:/温度|温湿度|temperature/i,word:/temperature/i},
    {key:'camera',label:'相机',ask:/摄像头|相机|camera/i,word:/camera/i},
    {key:'display',label:'显示',ask:/显示屏|屏幕|触摸屏|电子纸/i,word:/display|screen|epaper|e-paper/i},
    {key:'micro',label:'开发板',ask:/开发板|微控制器|单片机|development board/i,word:/development board|microcontroller|xiao/i},
    {key:'4g',label:'4G / LTE',ask:/\b4g\b|lte|蜂窝/i,word:/\b4g\b|\blte\b/i},
    {key:'robot',label:'机器人',ask:/机器人|机械臂|robot/i,word:/robot/i}
  ];
  const englishLabels={super:'Super mode',ether:'dual Ethernet',custom:'customization',gateway:'gateway',jetson:'Jetson edge inference',pi:'Raspberry Pi',fanless:'fanless',edge:'edge computing',din:'DIN rail',sensor:'sensors',temp:'temperature',camera:'camera',display:'display',micro:'development board',robot:'robotics'};
  if(en)for(const t of traits)t.label=englishLabels[t.key]||t.label;
  const searchable=new Map(products.map(p=>[p.sku,lower([p.name,p.summary,...(p.capabilities||[]),...p.groups,...(p.attributes||[]).map(a=>a.name+' '+a.value),...(p.modelSpecs||[]).map(a=>a.name+' '+a.value)].join(' '))]));
  function negated(query, t) {
    const clause=query.split(/[，,。;；\n]/).find(c=>t.ask.test(c));
    if(!clause)return false;
    const hit=clause.match(t.ask);
    return /(?:不需要|不要求|不用|无需|不要|不考虑|不必|without|do not need|no need for|don't need|no)\s*$/i.test(clause.slice(0,hit.index)) ||
      /^\s*(?:模式\s*)?(?:不需要|不用|无需|不要)/.test(clause.slice(hit.index+hit[0].length));
  }
  function intents(query){return traits.filter(t=>t.ask.test(query)&&!negated(query,t));}
  const normModel=s=>lower(s).replace(/seeed\s*studio|®|™/g,'').replace(/[^a-z0-9]/g,'');
  const heads=products.map(p=>{
    const first=p.name.split(/\s+(?:for|with|compatible with|powered by|–|-)\s+|[|,(（，]/i)[0];
    const head=normModel(first);
    return {p,head,full:normModel(p.name),qualified:first.trim().length!==p.name.trim().length};
  }).filter(a=>a.head.length>=5 && /\d/.test(a.head));
  const noAdapter=/无电源|无适配器|不(?:含|需(?:要)?)电源|自备\s*(?:适配器|电源)|(?:电源|适配器)\s*(?:由.{0,4})?自备|w\/o|without.*adapter|own power (?:supply|adapter)|no (?:power )?adapter/i;
  const gatewayModels=new Map();
  for(const p of products){
    const code=lower(p.name).match(/^recomputer\s+(r\d{4}(?:-\d+)?)\b/)?.[1];
    if(!code)continue;
    for(const alias of new Set([code,code.split('-')[0]])){
      gatewayModels.set(alias,gatewayModels.has(alias)?null:p);
    }
  }
  function matches(p,t) {
    if (t.yes) return t.yes(p);
    return t.word.test(searchable.get(p.sku));
  }
  function named(query) {
    const q=lower(query);
    const explicit = q.split(/[^a-z\d_-]+/).map(s=>bySku.get(s)).find(Boolean);
    if (explicit) return explicit;
    const gatewayCode=q.match(/\br\d{4}(?:-\d+)?\b/)?.[0];
    const gateway=gatewayCode&&gatewayModels.get(gatewayCode);
    if(gateway)return gateway;
    const model = (rx, sku) => rx.test(q) ? bySku.get(sku.toLowerCase()) : null;
    const j= model(/super\s*j4012|j4012\s+super\s*(?:版|款|$)/,'114110314') ||
      model(/rugged\s*j4012|j4012\s*rugged/,'100046979') ||
      model(/industrial\s*j4012|j4012\s*industrial/,'110110191') ||
      model(/robotics\s*j4012|j4012\s*robotics/,'114110310');
    if (j)return j;
    const nq=normModel(q);
    const candidates=heads.filter(a=>nq.includes(a.head)).sort((a,b)=>
      Number(nq.includes(b.full))-Number(nq.includes(a.full))||b.head.length-a.head.length||
      Number(a.qualified)-Number(b.qualified)||a.p.name.length-b.p.name.length);
    if(candidates.length && !['110110184','110110145'].includes(candidates[0].p.sku))return candidates[0].p;
    if (/(?:^|[^a-z0-9])j4012(?:$|[^a-z0-9])/.test(q)) return bySku.get(noAdapter.test(q)?'110110184':'110110145');
    for (const p of products) {
      if(p.series==='r11' && q.includes(lower(p.name.match(/\bR11\d\d(?:-10)?/i)?.[0]||'!nomodel!').slice(0,5)))return p;
    }
    if(q.includes('r1100'))return bySku.get('113991334');
    return null;
  }
  function score(p,q,needs) {
    const n=lower(p.name), s=searchable.get(p.sku);
    let points=0;
    for(const t of needs) if(matches(p,t)) {
      points+=t.word?.test(n)?9:4;
      if(t.key==='super' && p.series==='super')points+=16;
      if(t.key==='gateway' && p.series==='r11')points+=3;
    }
    const tokens=q.match(/[a-z0-9][a-z0-9.-]{1,}/g)||[];
    for (const w of new Set(tokens)) {
      if(/^(?:with|need|for|and|the|mode|is|in|at|it)$/.test(w))continue;
      if(n.includes(w))points+=Math.min(w.length,8);
      else if(s.includes(w))points+=1;
    }
    if(q.length>2 && n.includes(q))points+=24;
    if(p.sku.toLowerCase()===q)points+=1000;
    return points;
  }
  function lookup(query) {
    const q=lower(query.trim()), needs=intents(q), fixed=named(q);
    const ranked=products.map(p=>({p,score:score(p,q,needs)})).filter(x=>x.score>0)
      .sort((a,b)=>Number(a.p.storePageStatus==='not_found')-Number(b.p.storePageStatus==='not_found')||b.score-a.score||Number(Boolean(b.p.series))-Number(Boolean(a.p.series))||a.p.name.localeCompare(b.p.name));
    let selection='';
    if(fixed && !q.includes(fixed.sku.toLowerCase())){
      if(q.includes('r1100')&&!/r11[0-9][1-9]/.test(q))selection=pick('指定系列 · 展示 R1125-10 代表配置，请确认具体型号','Series match · R1125-10 shown as a representative configuration');
      else if(fixed.series==='classic'&&!noAdapter.test(q)&&!/含电源|带电源|with power adapter/i.test(q))selection=pick('指定型号 · 默认展示 Classic 含适配器版，请确认版本','Model match · Classic adapter bundle shown by default');
    }
    return {primary:fixed||ranked[0]?.p,explicit:!!fixed,needs,ranked,selection};
  }
  function alternatives(primary,q,needs) {
    const jetson = ['classic','super','jetson'].includes(primary.series);
    const r11=primary.series==='r11';
    const r10=/^reComputer\s+R10\d{2}-\d+\b/i.test(primary.name);
    const words=(lower(primary.name).match(/[a-z0-9-]{3,}/g)||[]).filter(w=>!['with','and','for','the','seeed','studio','module','product','compatible','with'].includes(w));
    const list=[];
    for (const p of products) {
      if(p.sku===primary.sku)continue;
      const name=lower(p.name), common=words.filter(w=>name.includes(w));
      const same=primary.groups.filter(c=>p.groups.includes(c));
      if(jetson && !['classic','super','jetson'].includes(p.series))continue;
      if(r11 && p.series!=='r11')continue;
      if(r10 && !/^reComputer\s+R10\d{2}-\d+\b/i.test(p.name))continue;
      if(!jetson && !r11 && (!common.length || (!same.length && common.length<2)))continue;
      const hits=needs.filter(t=>matches(p,t)), extra=hits.filter(t=>!matches(primary,t));
      const dismissed=traits.filter(t=>negated(q,t)).filter(t=>matches(p,t));
      const weight=extra.length*45+hits.length*6+Math.min(common.length,5)+Math.min(same.length,2)+
        (jetson&&p.series==='super'?8:0)+(r11&&p.sku==='100040889'?3:0)-dismissed.length*25;
      const labels=extra.map(t=>t.label).join(en?', ':'、');
      let why=extra.length?pick('可进一步核对的需求：'+labels+'。','Check this alternative for '+labels+'. '):'';
      if(jetson && p.series==='super')why+=pick('MAXN Super 可达 157 TOPS，提供双千兆网口。','Up to 157 TOPS in MAXN Super with dual Gigabit Ethernet.');
      else if(p.series==='classic')why+=pick('Classic 版，'+p.bundle+'，最高 100 TOPS。','Classic offers up to 100 TOPS, '+(p.sku==='110110184'?'without a power adapter.':'with a power adapter.'));
      else if(jetson && /rugged/i.test(p.name))why+=pick('IP66 防护和锁紧接头适合粉尘或喷水环境。','IP66 protection and locking connectors suit dusty or wet installations.');
      else if(p.sku==='110110191')why+=pick('无风扇，带串口和 PoE PSE 网口。','Fanless enclosure with serial I/O and PoE PSE.');
      else if(p.sku==='114110310')why+=pick('Robotics 载板支持选配 GMSL2 摄像头扩展板。','The Robotics carrier supports an optional GMSL2 camera expansion board.');
      else if(r11){const config=p.name.match(/\d+GB RAM\s*[,|，]?\s*\d+GB eMMC/i)?.[0]||p.name.split(' - ')[0];why+=pick('同属 R1100；该配置为 '+config+'。','R1100 configuration: '+config+'.');}
      else if(r10){
        const config=p.name.match(/\d+\s*GB\s+RAM\W+\d+\s*GB\s+eMMC/i)?.[0];
        why+=config?pick('R1000 系列，'+config+'。','R1000 configuration: '+config+'.'):pick('同属 reComputer R1000 系列。','Also in the reComputer R1000 family.');
      }
      else if(!why){const tokens=common.slice(0,3).join(en?', ':'、');why=pick((same.length?'同属 '+same[0]+'。':'')+'名称中的共同特征：'+tokens+'。',(same.length?'Also listed in '+same[0]+'. ':'')+'Shared product terms: '+tokens+'.');}
      list.push({p,weight,why});
    }
    return list.sort((a,b)=>Number(a.p.storePageStatus==='not_found')-Number(b.p.storePageStatus==='not_found')||b.weight-a.weight||a.p.name.localeCompare(b.p.name)).slice(0,3);
  }
  return {lookup,alternatives,matches,bySku};
}
if(typeof module!=='undefined')module.exports=createSearch;
