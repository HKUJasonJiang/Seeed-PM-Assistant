"""Reviewed drawings and variant columns reached through official overseas product pages."""
import re

CANBED="https://files.seeedstudio.com/products/102991674/CANBED%20DUAL%20-%20Longan%20Docs.pdf"
EMW="https://files.seeedstudio.com/products/113990976/tpyrced_DS0125EN_EMW3090_V2.6(2).pdf"
POE="https://files.seeedstudio.com/products/SenseCAP/%E6%B3%A8%E5%85%A5%E5%99%A8/SenseCAP%20PoE%20Injector%20(48V)%20Specification.pdf"
ODYS=(
    "https://files.seeedstudio.com/products/ODYSSEY_X86J4125_user_manual.pdf.pdf",
    "https://files.seeedstudio.com/wiki/ODYSSEY_X86J4125_v2/ODYSSEY_X86J4125_user_manual.pdf",
)
BOARD_V2={"102110763","102110764","102110765","102110766","102110767","102110768"}
BLUE_V2={"110991824","110991825"}
ACRYLIC="https://files.seeedstudio.com/products/110991984/Assembly%20instructions%20for%20Acrylic%20Enclosure.pdf"
MOUNT="https://github.com/SeeedDocument/Pi_screen/raw/master/res/Raspberry_mount.pdf"
WHEEL="https://github.com/SeeedDocument/Outsourcing/raw/master/%E9%BA%A6%E5%85%8B%E7%BA%B3%E5%A7%86%E8%BD%AE%E5%B0%8F%E8%BD%A6/Mecanum%20wheel%20car%20assembly%20instruction%20manual.pdf"
CREATOR_GUIDE="https://files.seeedstudio.com/products/110020230/Grove-Creator-Kit-ganma.pdf"
RK3399="https://github.com/SeeedDocument/Outsourcing/raw/master/TB-RK3399Pro/tb-rk3399prod_33101_20181217.pdf"
CANBED_MOUNT="https://files.seeedstudio.com/Installation%20Hole%20Position%20Diagram.pdf"
EDITIONS={
    ACRYLIC:("0f3bd8fdcd5e8f8d9e756685d061499031e7cd8bf21174824adf4b36aa8ffcfa",3),
    MOUNT:("7ab1c9bda155000aae6ad986636fc85b51d19ce766937864ad7a797dc27e57dc",11),
    WHEEL:("745308d64088777e9656140d9e593ef1587a568e1c48b226ad2d8d739b3eb691",5),
    CREATOR_GUIDE:("2f5a4bf928d6c7a90c487ad3bf0cf517d4f7708ec97636abecfcd85d1161320a",108),
    RK3399:("b56dc2c2275c71e98e76d0854e2e4682f660de73ad4ae0a956c04fc72a1a04b0",36),
    CANBED_MOUNT:("cdd8c1ade574045aa92c1d4a1f9b2f14910f6917663222da5d9285f3a1232355",5),
    CANBED:("0e09dcd7a992d3adce3e310f7ad672cec909070b1af872dc197f55539f4fe8be",11),
    EMW:("a3f5eb21b00d170f0bc6521a7dd9d76ddc2d4c1896e80880e864e071831a4491",29),
    POE:("85baebf0970a4be0f538762e06900eabdaa22fdb2c653bb05a6599928112d8c0",3),
    **{u:("b76351544cf1af271673597e7bee483606c1c1c119fe3b276fc7fa6b70519384",16) for u in ODYS},
}


def figure_scope(url,product,record):
    if (record.get("sha256"),record.get("pages"))!=EDITIONS.get(url):return None
    sku=product["sku"]
    if url==ACRYLIC and sku in {"110991984","E24072601"}:
        return "component_guide",[(1,"assembly_components","Enclosure assembly steps 1–2, including eight cut strips of tape"),
                                  (2,"assembly_components","Enclosure assembly steps 3–4, including PM2 × 6 mm screws and foam pads")]
    if url==MOUNT and sku in {"104990443","104990444"}:
        return "application",[(1,"application","Photographic installation guide for mounting a Raspberry Pi to the display")]
    if url==WHEEL and sku=="110090322":
        return "component_guide",[(1,"assembly_components","Illustrated mecanum chassis assembly steps"),(5,"assembly_components","Completed motor and wheel placement")]
    if url==CREATOR_GUIDE and sku in {"110020228","110020229","110020230","E23020721"}:
        return "application",[(102,"example_configuration","Smart music box example materials"),(103,"example_configuration","Smart garden example materials"),
                              (104,"example_configuration","Smart cup example materials")]
    if url==RK3399 and sku=="110110064":
        return "component_guide",[(1,"assembly_components","RK3399Pro evaluation board schematic"),(4,"assembly_components","Circuit system block diagram")]
    if url==CANBED_MOUNT and sku=="102991776":
        return "component_guide",[(1,"assembly_components","Mechanical drawing of the enclosure and installation holes")]
    return None


def reviewed(url,p,rec):
    if (rec.get("sha256"),rec.get("pages"))!=EDITIONS.get(url):return [],[]
    sku,title=p["sku"],p.get("name","")
    def row(kind,name,page,scope="sku",**fields):
        return dict(kind=kind,name=name,source=url+"#page="+str(page),scope=scope,basis="reviewed_model_variant_table",**fields)
    if url==ACRYLIC and sku=="110991984" and title.startswith("Acrylic Enclosure for reSpeaker Lite"):
        facts=[row("modelSpec","Enclosure assembly step 2 / 外壳装配步骤 2",1,
                   value="8 cut strips of double-sided tape / 使用 8 段裁好的双面胶")]
        notes=[]
        for name,quantity in p.get("parts",[]):
            if "PM2.0_H6.0mm" in name and str(quantity).strip(" x×")=="4":
                label="PM2 × 6 mm screws · assembly step 4 uses 6 / 装配步骤 4 用量为 6 颗"
                listed=name+" · 4 in the store packing list / 商城标配 4 颗"
            elif "EVA Foam - 16_16_8" in name:
                label="EVA foam in assembly step 4 / 装配步骤 4 所示泡棉 10 × 10 × 8 mm"
                listed=name+" · "+str(quantity)+" in the store packing list / 商城标配"
            else:continue
            notes.append({"publishedSku":"","field":"assemblyUsage","name":label,"catalogName":listed,
                          "source":url+"#page=2","catalogUrl":p.get("partSources",{}).get(name) or p.get("partSource") or p.get("url","")})
        return facts,notes
    if url==CANBED and sku=="102991674" and title.startswith("CANBed DUAL"):
        rows=[("CANBed Dual PCBA","1"),("6 Pin Terminal connector","1"),("6 Pin Switch","2"),("9x2 2.54 Header","1"),("3x2 2.54 Header","1")]
        facts=[row("inbox",n,6,quantity=q) for n,q in rows]
        # The supplier explicitly offers this after purchase. This is not a
        # Seeed factory customization or a replacement for the default bare kit.
        facts.append(row("modelSpec","Connector assembly",5,value="Plug-in parts ship unsoldered. The guide says the board supplier, Longan Labs, can arrange soldering after purchase."))
        return facts,[]
    if url==EMW and sku=="113990976" and title.startswith("EMW3090V2 WI-FI Module"):
        options=[("MXKIT-Base","development board for all EMW3090 modules"),("MXKIT-Core-3090","core board used with MXKIT-Base"),
                 ("FX-3090","production fixture with MXKIT-Base and MXKIT-Core-3090 test boards")]
        return [row("accessory",code+" — "+desc,2,"family",family="EMW3090",namedAccessory=True,manufacturerCode=code) for code,desc in options],[]
    if url==POE and sku=="114992951" and title.startswith("SenseCAP PoE Injector (48V) EU"):
        return [row("inbox","SenseCAP PoE Injector (48V)",1,quantity="1"),row("inbox","Power Cable",1,quantity="1"),
                row("modelSpec","Supported gateway families",1,value="SenseCAP M1 and SenseCAP M2, for PoE-enabled devices")],[]
    if url not in ODYS or sku not in BOARD_V2|BLUE_V2:return [],[]
    if sku in BOARD_V2 and not re.match(r"^ODYSSEY - X86J4125(?:864|800) v2\b",title,re.I):return [],[]
    if sku in BLUE_V2 and not re.match(r"^ODYSSEY Blue J4125 v2\b",title,re.I):return [],[]
    telec="TELEC" in title.upper()
    existing={n.casefold().replace(" ",""):n for n,q in p.get("parts",[])}
    # The blue computer is a different bundle. Corroborate only rows already
    # present in the exact storefront list, including the assembled cooling fan.
    g=[("User Manual","1"),("Antenna","2"),("RTC Battery","1"),("Heat Sink(Assembled)","1")]
    if sku in BOARD_V2:g.append(("SATA Cable","1"))
    if "864" in title or sku in BLUE_V2:g.append(("Cooling Fan(Assembled)","1"))
    facts=[row("inbox",existing[k],2,"family",family="ODYSSEY X86J4125 v2",quantity=q) for n,q in g if (k:=n.casefold().replace(" ","")) in existing]
    supply=next((n for n,q in p.get("parts",[]) if re.search(r"international power adapt[eo]r",n,re.I)),None)
    conflicts=[]
    if telec and supply:
        conflicts.append({"publishedSku":"","field":"guidePackageScope","name":"The v2 manual excludes the international power adapter from the TELEC version",
                          "catalogName":supply,"catalogUrl":p.get("partSources",{}).get(supply) or p.get("partSource") or p.get("url",""),"source":url+"#page=2"})
    elif telec:
        facts.append(row("exclusion","International power adapter (TELEC version)",2))
    elif supply:
        facts.append(row("inbox",supply,2,quantity="1",modelSource=url+"#page=15"))
    elif p.get("parts"):
        conflicts.append({"publishedSku":"","field":"guidePackageScope","name":"V2 manual lists one international power adapter for non-TELEC versions",
                          "catalogName":"Power adapter is unlisted in this storefront packing table","catalogUrl":p.get("partSource") or p.get("url",""),"source":url+"#page=2"})
    return facts,conflicts
