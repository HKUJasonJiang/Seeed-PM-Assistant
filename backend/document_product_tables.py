"""Edition-specific packing and option tables checked against the actual PDF pages."""
import re
from .document_reviewed import FLYER_ACCESSORIES

WEATHER="https://files.seeedstudio.com/products/SenseCAP/SenseCAP_ONE/SenseCAP_ONE_V3_Compact_Weather_Station_User_Guide_V1.6.pdf"
WEATHER17="https://files.seeedstudio.com/wiki/SenseCAP/SenseCAP%20ONE%20Compact%20Weather%20Sensor_/SenseCAP_ONE_V3_Compact_Weather_Station_User_Guide_V1.7.pdf"
OUTDOOR="https://files.seeedstudio.com/products/SenseCAP/outdoor_gateway/LoRaWAN%20Outdoor%20Gateway%20Userguide.pdf"
GATEWAY_ADAPT="https://sensecap-docs.seeed.cc/pdf/Guide-for-SenseCAP-Adaption-to-3rd-Party-Gateways-Servers-V1.2.pdf"
GATEWAY_ADAPT_ALT="https://files.seeedstudio.com/products/SenseCAP/102991155/Guide%20for%20SenseCAP%20Adaption%20to%203rd%20Party%20Gateways%20&%20Servers-V1.2.pdf"
WEATHER_SENSOR_V2="https://files.seeedstudio.com/products/SenseCAP/SenseCAP_ONE/SenseCAP_ONE_V2_Compact_Weather_Station_User_Guide.pdf"
INVENTOR_GUIDE="https://files.seeedstudio.com/wiki/Grove_kit_for_microbit/res/Guide_Grove_kit_for_microbit.pdf"
INVENTOR_MIRROR="https://files.seeedstudio.com/wiki/Grove-Shield-for-microbit-v2/res/Guide_Grove_kit_for_microbit.pdf"
NOSE_BOARD="https://www.seeedstudio.com/document/hanahotaru_manual.pdf"
LORA_CERT="https://files.seeedstudio.com/wiki/Seeeduino_LoRa/res/ce-rhf76-052.pdf"
EAGLE_CERT="https://files.seeedstudio.com/Seeed_Certificate/documents_certificate/114991433-CE.pdf"
SCREENING_KIT="https://files.seeedstudio.com/products/114992189/Remote%20AI%20Temperature%20Screening%20System%20114992189.pdf"
ODYSSEY_BLUE="https://files.seeedstudio.com/wiki/Odyssey_Blue_J4125/Odyssey_Blue_J4125_128GB_user_manual.pdf"
DT71="https://files.seeedstudio.com/products/110991444/DT71MiniDigitalTweezersUserManualENV1.08.pdf"
QSCOUT="https://github.com/SeeedDocument/Outsourcing/raw/master/110090181/img/Q-Scout-Part%20List.pdf"
DEMO_KITS="https://files.seeedstudio.com/products/SenseCAP/all-in-one%20weather%20station%20Kit/User%20Guide.pdf"
LINKIT_BOX="https://files.seeedstudio.com/wiki/Grove-Starter_Kit_for_LinkIt_ONE/res/Parts_List_Grove_Starter_Kit_for_LinkIt_ONE.pdf"
EMC3080="https://files.seeedstudio.com/products/113990975/EMC3080EN.pdf"
JNCRADIO="https://files.seeedstudio.com/wiki/JNCRadio/DATASHEET_Chelegance-VNA-3G-Specifications.pdf"
UARM="https://statics3.seeedstudio.com/assets/file/bazaar/product/uArm_Swift_Specifications.pdf"
PUPPY="https://www.seeedstudio.com/document/pdf/Puppy%20Instruction%20manual.pdf"
LORA_PI_KIT="https://github.com/SeeedDocument/LoRaWAN_Gateway-868MHz_Kit_with_Raspberry_Pi_3/raw/master/res/LoRa_LoRaWan_Gateway_Kit.pdf"
ROBOTICS="https://files.seeedstudio.com/products/NVIDIA-Jetson/reComputer_robotics_J401_user_manual.pdf"
ROBOTICS_ALT="https://files.seeedstudio.com/products/NVIDIA-Jetson/reComputer_robotics_J401_datasheet.pdf"
SUPER="https://files.seeedstudio.com/products/NVIDIA-Jetson/reComputer_super_user_manual.pdf"
INDUSTRIAL="https://files.seeedstudio.com/products/NVIDIA/reComputer-Industrial-Reference-Guide.pdf"
NVR="https://files.seeedstudio.com/wiki/reServer-Industrial/reServer-Industrial-Reference-Guide.pdf"
NVR_BRIEF="https://files.seeedstudio.com/wiki/reServer-Industrial/reServer-Industrial-Datasheet.pdf"
J401B="https://files.seeedstudio.com/wiki/reComputer/reComputer_J401B_datasheet_v1.pdf"
T906="https://files.seeedstudio.com/wiki/AI_Computer_T906/Mini_AI_Computer_T906_datasheet.pdf"
PLANT="https://files.seeedstudio.com/wiki/Grove_Smart_Plant_Care_Kit/res/Part_list_grove_smart_plant_care_kit_processed.pdf"
R1_FLYER="https://files.seeedstudio.com/wiki/reComputer-R1000/reComputer-R1100/reComputer-R1100-flyer.pdf"
BEAGLE="https://files.seeedstudio.com/wiki/BeagleV-Ahead/BeagleV-Ahead_Datasheet-by_Seeed-Studio.pdf"
DIGESTS={
    WEATHER:"5910b1edff0644e4b936b43cffcb27e89fb4e29646093dd9d7b91a64de56b161",
    WEATHER17:"dbbcd419deff9871080b4353914c6c2bda266b343246178bdc6b705c47c925d4",
    OUTDOOR:"4b5ef5396c89dc3cba86c857718c19177661be19c65c501feeb0f378dd3f1180",
    GATEWAY_ADAPT:"39dd895f1c7499ac5938a08b27606fadb3ec2edd81df110df14071c584b42cb8",
    GATEWAY_ADAPT_ALT:"3651b7981f74224f1088be883d58620fd26fe6a3144282e15de114ac7ea374aa",
    WEATHER_SENSOR_V2:"079e82a8d2b3468c806ef610a02a842342bd57958d591b54b675e36a901a8142",
    INVENTOR_GUIDE:"dee66f093628024fc8cb030fcd2f2aa4afe24bf0d38de6a747dde318248df86b",
    INVENTOR_MIRROR:"dee66f093628024fc8cb030fcd2f2aa4afe24bf0d38de6a747dde318248df86b",
    NOSE_BOARD:"6aabb506feaffaa7b91ea7847d882f69e36121b8fc1cb75de1e754bbea8e5247",
    LORA_CERT:"8c1ef5b0bc4ad5031032620730aa2d66a28c89f8aa1c4792df290789c60a4481",
    EAGLE_CERT:"4f7736146dd7544d097256045726d587ed8ee95b122dc8e1ccfc9311f6698a09",
    SCREENING_KIT:"d4e352bdde9213c2a3f32349747eee8ecb6861c1fab5eba19c4158025563f9dd",
    ODYSSEY_BLUE:"5af0a0b98b386d168d526274703e3665c932d1f3a6ce864b0683f4253d3e52b8",
    DT71:"acdf8094f6cea957075d26b4ec714ab90acae8d5b84aea5fc193803c40781ecf",
    QSCOUT:"f2b1dd58f1797ab1f724412a091f9f1ee1f78a926d74bda88df99d6c7ee2f718",
    DEMO_KITS:"367b9e559425687c8feed4310f408ed57398eec7f58b41db65fafdf6033f0c12",
    LINKIT_BOX:"f28183ed432e7012d1d161121fb2482a15e8d87408cf50891426bf35c82c1e8a",
    EMC3080:"0378dfbe2015ff15fab47064533a58edc44df92cc0f9fce8b20ca2e28928ca68",
    JNCRADIO:"4743e3ef3430cc6a9b026e9b47b03197da354d2876f893de6ae94ef8341a2568",
    UARM:"a1ef6282bec3cf2c0e2a491da0fbd331ab57543ea83bdf38b5e04f464ed2b1b1",
    PUPPY:"a2553324005d7c7f75af11ac37e39138b1399e30649a190baebcad84ca7e7be7",
    LORA_PI_KIT:"ce5f3bc1a92da3564d754d39505e44f72f963f38cff6d3fe0683b42af7df75ec",
    ROBOTICS:"c3aaa001d57a0c2c76373a277741930e8633ed7e9f4affbe2216340bec917ba1",
    ROBOTICS_ALT:"ee11fc915adc3d8bd7bae3595db8ebba87e0f946381ce2a666b53e43b20eb92e",
    SUPER:"8dda6e84e67b4df852eb8926e3488295d28fbbbab9212b8e8139d205a496e6ec",
    INDUSTRIAL:"41af2f7d7b60cf7118f673eb6a95deef6485976e036cd780cb204df89f971af5",
    NVR:"4f692b1dd5710ed248567c815fa55e9c25d21bafdb12f1f1ac8fb2f048d1a1d9",
    NVR_BRIEF:"918d2b4a0e4f66d4a5f306149e084b8fda842260359deefa1fe943a346edb5cf",J401B:"a677ad40ad6806a042b184b7077864f21ec74f01ad68a24fc5df203fc8bfe43e",
    T906:"16a8ceee90a7d15d17a34439becec005916403275032a0fdfb58018f4b00853a",
    PLANT:"e4673aab9d0f4896b98c45ecaec3edac84ec7e210636e607d2f5b889fe5deca1",R1_FLYER:"fa58ddbe0b8ba1d9de0208e2d2df3149823de450c21908a42706f3292ea108b6",
    BEAGLE:"63030a07ca50a95375359078d00dce7db885c22d4847819059372494b411d5e3",
}
WEATHER_MODELS={
    "101991044":"S200","101990693":"S500","101991021":"S500","101991232":"S600-A","101990787":"S700",
    "101991022":"S700","101991050":"S700-A","101991102":"S700-B","101991141":"S700-C","101991023":"S800",
    "101990784":"S900","101990902":"S1000","101991024":"S1000",
}
ROBOTS={"114110308":("J3011","Orin Nano 8GB"),"114110309":("J4011","Orin NX 8GB"),"114110310":("J4012","Orin NX 16GB")}
SUPER_MODELS={"114110311":("J3010","Orin Nano 4GB"),"114110312":("J3011","Orin Nano 8GB"),
              "114110313":("J4011","Orin NX 8GB"),"114110314":("J4012","Orin NX 16GB")}
INDUSTRIAL_MODELS=dict(zip(("110110188","110110189","110110190","110110191","110110192","110110193"),
                           ("J2011","J2012","J4011","J4012","J3010","J3011")))
NVR_MODELS={"114110247":"J4012","114110248":"J4011","114110249":"J3011","114110250":"J3010"}
B_MODELS={"114993486":("J3010B","Orin Nano 4GB"),"114993487":("J3011B","Orin Nano 8GB"),
          "114993488":("J4011B","Orin NX 8GB"),"114993489":("J4012B","Orin NX 16GB")}
FAMILIES={WEATHER:("SenseCAP ONE V1 / V2",9),ROBOTICS:("reComputer Robotics J401",7),ROBOTICS_ALT:("reComputer Robotics J401",7),
          WEATHER17:("SenseCAP ONE V1 / V2",9),OUTDOOR:("SenseCAP LoRaWAN Outdoor Gateway",0),GATEWAY_ADAPT:("SenseCAP LoRaWAN Outdoor Gateway",0),
          GATEWAY_ADAPT_ALT:("SenseCAP LoRaWAN Outdoor Gateway",0),
          INDUSTRIAL:("reComputer Industrial",3),NVR:("reServer Industrial",3),NVR_BRIEF:("reServer Industrial",1),
          R1_FLYER:("reComputer R1xxx",1),SUPER:("reComputer Super J401",7)}
ROBOT_OPTIONS={
    66:[("112990246","256GB NVMe M.2 SSD"),("112990247","512GB NVMe M.2 SSD"),("112990267","1TB NVMe M.2 SSD"),
        ("114993467","2TB NVMe M.2 SSD"),("E24121001","RTL8822CE wireless NIC kit"),("313080684","19V / 4.74A power adapter"),
        ("313990332","C5 AC power cord, US"),("313990328","C5 AC power cord, UK"),("106990469","C5 AC power cord, JP"),
        ("106990468","C5 AC power cord, EU"),("106990470","C5 AC power cord, CN"),
        ("323030949","Metal panel mounting holder for reComputer Jetson"),("317990026","CH340G USB-to-TTL adapter"),
        ("114992738","RPLiDAR S2 30 m scanner"),("110991068","RPLiDAR A3M1 25 m scanner")],
    67:[("114992561","RPLiDAR A1M8-R6 12 m scanner"),("101090061","RPLiDAR C1M1-R2 12 m scanner"),
        ("107990193","reSpeaker USB microphone array"),("114992262","IMX219-130 camera, 130°"),("114992265","IMX219-200 camera, 200°"),
        ("114992264","IMX219-160IR camera, 160°"),("114993032","IMX477R Raspberry Pi HQ camera"),("114993029","IMX708 Camera Module 3 NoIR")],
}
SUPER_CELLULAR=[("113991134","EC25-AFXGA mini-PCIe LTE module, North America"),("113991135","EC25-EUXGR mini-PCIe LTE module, EMEA and Thailand"),
                ("113991174","EC25-AUXGR mini-PCIe LTE module, Australia"),("113991214","EC25-EFA mini-PCIe LTE module, Thailand"),
                ("113991234","EC25-EMGA mini-PCIe LTE module, Malaysia"),("113991296","EC25-JFA mini-PCIe LTE module"),
                ("110061502","4G antenna kit"),("110061521","GPS antenna kit for EC25")]


def reviewed_edition(url,record):
    return bool(url in DIGESTS and record.get("sha256")==DIGESTS[url])


def sections_outside_product_box(url,record,product):
    """Keep useful page links while distinguishing a project, one component, or an internal BOM."""
    if not reviewed_edition(url,record):return None
    code=product["sku"]
    if url in (INVENTOR_GUIDE,INVENTOR_MIRROR) and code=="110060762":
        names=["Control the Light","Sunshine micro:bit","LED Bar Control","Music Player","Gesture Recognition",
               "Smart Guard","Shake Counter","Ultrasonic Meter","Rainbow on the Desk","Guardians of the Secrets in Your Bag",
               "Guardians of the Secrets in Your Room","Magic Musician"]
        return "application",[(page,"example_configuration",name) for page,name in enumerate(names,5)]
    if url==WEATHER_SENSOR_V2 and code in ("E23010807","E23010808"):
        return "component_guide",[(8,"component_guide","Weather sensor package and separately purchased mounting fittings")]
    if url==NOSE_BOARD and code in ("110990217","110990218"):
        return "component_guide",[(8,"assembly_components","Parts on the assembled sensor PCB")]
    if url==LORA_CERT and code=="102010129":
        return "certification",[(2,"certification","Technical construction file checklist for CE review")]
    if url==EAGLE_CERT and code=="114991433" and product.get("name","")=="Eagleye 530s":
        return "certification",[(2,"certification","Accessory field on the Eagleye 530s conformity assessment: N/A")]
    if url==DT71 and code=="110991444" and product.get("name","").startswith("DT71 Mini Digital Tweezers"):
        return "application",[(14,"application","Calibration instructions refer to a downloadable resource")]
    return None


def printed_weather_matches(product,record):
    code=product["sku"];model=WEATHER_MODELS.get(code)
    return bool(model and code in record.get("pageSkus",{}).get("9",[]) and re.search(r"^SenseCAP (?:ONE )?"+re.escape(model)+r"(?![A-Z0-9-])",product.get("name",""),re.I))


def original_odyssey_blue(product):
    code=product["sku"];title=product.get("name","").casefold()
    listed={name for name,qty in product.get("parts",[])}
    return (code in {"110991564","110991565"} and title.startswith("odyssey blue:") and "j4125" in title and "128gb" in title
            and " v2" not in title and "ODYSSEY - X86J4125" in listed and "User Manual" in listed
            and ("telec" in title)==(code=="110991565") and (code=="110991565" or "International Power Adapter" in listed))


def source_rows(url,product,record,catalog=None):
    if not reviewed_edition(url,record):return []
    code=product["sku"];name=product.get("name","")
    rows=[]
    def fact(kind,title,page,scope="family",**fields):
        if scope=="family":
            family,model_page=FAMILIES.get(url,("reComputer J401B",3 if B_MODELS.get(code,("",))[0].startswith("J30") else 4))
            fields["family"]=family
            if model_page:fields["modelSource"]=url+"#page="+str(model_page)
            elif product.get("url"):fields["modelSource"]=product["url"]
        rows.append({"kind":kind,"name":title,"scope":scope,"source":url+"#page="+str(page),
                     "basis":"reviewed_manufacturer_table","documentUrl":url,**fields})
    def package(entries,page,scope="family"):
        for title,quantity in entries:fact("inbox",title,page,scope,quantity=str(quantity))
    def optional(names,page,excluded=False):
        for title in names:
            fields={"namedAccessory":True}
            secondary={"TPM2.0 module with Infineon SLB9670":("114993114","tpm20modulewithinfineonslb9670"),
                       "Wio-WM1302 LoRaWAN gateway module (SPI, US915-M)":("114992969","wiowm1302lorawangatewaymodulespius915m")}
            if title in secondary and catalog:
                sku,prefix=secondary[title];target=catalog.get(sku,{})
                clean=re.sub(r"[^a-z0-9]","",target.get("name","").casefold())
                if clean.startswith(prefix) and target.get("url"):fields.update(sku=sku,storeProductSource=target["url"])
            if excluded:fields["notIncludedSource"]=url+"#page="+str(page)
            fact("accessory",title,page,**fields)
            if excluded:fact("exclusion",title,page)
    if url in (WEATHER,WEATHER17) and printed_weather_matches(product,record):
        package([("SenseCAP ONE compact weather sensor",1),("M12 8-pin communication cable",1),("USB Type-C configuration cable",1)],8)
        optional(["Flange plate","Pole adapter sleeve base","Pole adapter cross bar"],8,True)
    elif url in (OUTDOOR,GATEWAY_ADAPT,GATEWAY_ADAPT_ALT) and code in {"102991154","102991155","114992548","102991375"}:
        region={"102991154":"EU868","102991155":"US915","114992548":"AU915","102991375":"AS923"}[code]
        if not re.match(r"^SenseCAP Outdoor Gateway\s*[-–]\s*LoRaWAN "+region+r"(?:MHz)?\b",name,re.I):return []
        page={OUTDOOR:41,GATEWAY_ADAPT:76,GATEWAY_ADAPT_ALT:77}[url]
        package_items=[("Long Range Gateway",1),("Long Range Antenna",1),("4G Antenna",1),("Allen Hex Key",1),
                       ("Mounts",4),("Power Adapter",1),("Power Extension Cable (5M)",1),("Ferrules / Aluminum piece","2 / 2"),
                       ("M5 Self-drilling Screws",8)]
        # The regional store page corroborates quantities and optional roles.
        # In particular AS923 is not established by a server-address example.
        if code=="102991375":
            shop={p[0].lower():str(p[1]).lower().replace("x","").replace(" ","") for p in product.get("parts",[]) if len(p)>1}
            if url!=GATEWAY_ADAPT or any(shop.get(n.lower())!=str(q).replace(" ","") for n,q in package_items):return []
        package(package_items,page)
        aliases={"Antenna lightning protector":"Antenna Lightning Protector","LoRa antenna brackets":"Long Range Antenna Brackets",
                 "LoRa fiberglass omnidirectional antenna":"Long Range Fiberglass Omni Antenna"}
        optional(list(aliases)[:2],page)
        optional([list(aliases)[2]],page,True)
        for item in rows:
            if item["kind"]=="accessory" and any(a.get("name")==aliases[item["name"]] for a in product.get("accessories",[])):
                item["storeLabel"]=aliases[item["name"]]
    elif url==DEMO_KITS and code=="E23010807" and name.startswith("SenseCAP IoT 4G Solution Demo Kit"):
        label="High-efficiency Waterproof PV-12W Solar Panel"
        item={"namedAccessory":True,"storeProductSource":product.get("url","")+"#:~:text=option%20to%20purchase%20solar%20panels"}
        matches=[p for p in (catalog or {}).values() if p.get("name","").startswith(label)]
        if len(matches)==1 and matches[0].get("url"):item.update(sku=matches[0]["sku"],matchingProductUrl=matches[0]["url"])
        fact("accessory",label,1,"sku",**item)
    elif url==DEMO_KITS and code=="E23010808" and name.startswith("SenseCAP IoT LoRaWAN"):
        shop=product.get("url","")
        if shop:
            source=shop+"#:~:text=Optionally%2C%20enhance%20your%20setup%20with%20a%20power%20adapter"
            rows.append({"kind":"accessory","name":"Power adapter (optional)","namedAccessory":True,"scope":"sku",
                         "source":source,"basis":"document_configuration_and_explicit_store_option","documentUrl":url,
                         "modelSource":url+"#page=11"})
    elif url==LINKIT_BOX and (code,name)==("110060039","Grove Starter Kit for LinkIt ONE") and record.get("pages")==1:
        printed=["Grove Touch Sensor","Grove Sound Sensor","Grove - Light Sensor","Grove - Servo","Grove - Dust Sensor",
                 "Grove – Temperature & Humidity Sensor Pro","Grove - UV Sensor","Grove – Barometer",
                 "Grove - 3-Axis Digital Accelerometer(±16g)","Grove - Led Bar","Grove - Base Shield","Manual"]
        aliases={"Grove Touch Sensor":"Grove - Touch","Grove Sound Sensor":"Grove - Sound Sensor",
                 "Grove – Temperature & Humidity Sensor Pro":"Grove - Temperature & Humidity Sensor Pro",
                 "Grove – Barometer":"Grove - Barometer Sensor","Manual":"Grove Guide"}
        store={r[0] for r in product.get("parts",[]) if len(r)>1 and str(r[1]).strip("x× ")=="1"}
        for num,actual in enumerate(printed,1):
            retail=aliases.get(actual,actual)
            if retail in store:fact("inbox",retail,1,"sku",quantity="1",documentItem=actual,printedItemNumber=num)
    elif url==SCREENING_KIT and (code,name)==("114992189","Remote AI Temperature Screening System") and record.get("pages")==14:
        package([("AI detector",1),("Terminal",1),("Power adapter",2),("USB cable",1)],7,"sku")
    elif url==ODYSSEY_BLUE and original_odyssey_blue(product):
        package([("ODYSSEY - X86J4125",1),("User Manual",1)],1,"sku")
        if code=="110991565":fact("exclusion","Power adapter (TELEC version)",1,"sku")
        else:fact("inbox","International Power Adapter",1,"sku",quantity="1",storeProductSource=product.get("partSource") or product["url"])
        fact("exclusion","Keyboard and mouse (customer-provided)",1,"sku")
    elif url==EMC3080 and code=="113990975" and name.startswith("EMC3080 "):
        for title in ("MXKIT-Base development board","MXKIT-Core-3080 development core board (used with MXKIT-Base)",
                      "FX-3080 production fixture with MXKIT-Base and MXKIT-Core-3080"):
            fact("accessory",title,2,"sku",namedAccessory=True)
    elif url==JNCRADIO and code=="113991034" and "VNA" in name and "JNCRadio" in name:
        # The manual's list includes the instrument itself. The six named
        # pieces and their quantities also occur in this exact SKU's store box.
        names={"JNCRadio VNA 3G":1,"SMA-KK adapter":1,"SMA-JJ adapter":1,"SMA-JKW adapter":1,"USB Type-C cable":1,"Stylus":1}
        for label,qty in product.get("parts",[]):
            normalized=re.sub(r"\s+[x×]\s*\d+$","",label,flags=re.I)
            if normalized in names and re.fullmatch(r"\s*[x×]?\s*1\s*",str(qty),re.I):
                fact("inbox",label,5,"sku",quantity="1",storeProductSource=product.get("partSource") or product.get("url",""))
    elif url==UARM and (code,name) in {("110991030","uArm Swift"),("110991031","uArm Swift Pro")}:
        # Side-by-side column headers distinguish the two finished arms.
        values=("6V DC","5 mm","167 mm/s") if code=="110991030" else ("12V DC","0.2 mm","100 mm/s")
        for label,value in zip(("Input voltage","Repeatability","Maximum speed"),values):
            fact("modelSpec",label,1,"sku",value=value)
    elif url==LORA_PI_KIT and code=="110060622" and name=="LoRa LoRaWAN Gateway - 868MHz Kit with Raspberry Pi 3":
        names={item[0] for item in product.get("parts",[]) if str(item[1]).strip("x× ")=="1"}
        aliases={"Gateway module RHF0M301–868":"Gateway module RHF0M301 – 868",
                 "Seeeduino LoRaWAN with GPS (RHF76-052AM)":"Seeeduino LoRaWAN with GPS"}
        for row in record.get("rows",[]):
            label=aliases.get(row["name"],row["name"])
            if row.get("kind")=="inbox" and row.get("quantity")=="1" and row["source"].endswith("#page=2") and label in names:
                fact("inbox",label,2,"sku",quantity="1",storeProductSource=product.get("partSource") or product.get("url",""))
                rows[-1]["source"]=row["source"]
    elif url==PUPPY and code=="110990106" and name=="Playful Puppy Quadruped Robot Kit":
        # The manufacturer numbers 36 drawing cells. The paired adhesive strips
        # are two pieces within one numbered cell. Keep these quantity checks
        # separate from any assembly steps or parts pulled from the drawings.
        quantities={"Base plate":1,"9g geared motor":10,"Round servo horn":4,"Servo horn-2":4,"9g servo clutchplate":2,
                    "Clutch-drop shape":1,"Leg segment":8,"5x3mm magnet":16,"EVA feet":4,"Servo mounting bracket":1,
                    "Pan-tilt bracket-1":1,"Pan-tilt bracket-2":1,"M2.6*12 self-tapping screw with flange":4,
                    "M2.2*8 self-tapping screw":16,"M2*5 self-tapping screw with flange":6,"M2*6 self-tapping screw with flange":16,
                    "M2*6 self-tapping screw":12,"M2*8 self-tapping screw with flange":4,"M2.3*12 self-tapping screw":2,
                    "M2.6*8 self-tapping screw":2,"M3*6 screw":10,"M3*8 screw":2,"M3 nut":10,
                    "M3 Nyloc nut":1,"Washer":5,"L9 brass spacer":4,"L30 brass spacer":4,"Velcro adhesive strips male":1,
                    "Velcro adhesive strips female":1,"L15 spacer":1,"Glassine washer":4,"IR compound eye":1,
                    "Mini Driver board":1,"Battery holder":1,"Clutch-elliptical shape":1,"7 core rainbow cable":1,"Spiral wrap tail":1}
        for label,quantity in quantities.items():
            fact("inbox",label,4,"sku",quantity=str(quantity))
    elif url==SUPER and code in SUPER_MODELS:
        model,module=SUPER_MODELS[code]
        if code not in record.get("pageSkus",{}).get("7",[]) or not re.match(r"^reComputer Super "+model+r"\s*[-–]",name,re.I):return []
        package([("Jetson "+module+" module",1),("Seeed Carrier Board (reComputer Super J401)",1),
                 ("Aluminum Case and Heatsink with Fan",1),("USB Cable; Type A to Type C",1),("User Manual",1)],2)
        fact("inbox","128GB NVMe SSD",64,quantity="1",sku="112990226",quantitySource=url+"#page=2")
        first={k:v for k,v in ROBOT_OPTIONS[66]}
        for sku in ("112990246","112990247","112990267","114993467","E24121001","313990332"):
            fact("accessory",first[sku],64,sku=sku)
        for sku,label in SUPER_CELLULAR:fact("accessory",label,64,sku=sku)
        if "Nano" in module:fact("accessory","12V / 5A power adapter for Orin Nano",64,sku="313080482")
        else:fact("accessory","19V / 4.74A power adapter for Orin NX",64,sku="313080684")
        for sku in ("313990328","106990469","106990468","106990470","323030949","317990026","114992738","110991068"):
            fact("accessory",first[sku],65,sku=sku)
        for sku,label in ROBOT_OPTIONS[67]:fact("accessory",label,65,sku=sku)
    elif url in (ROBOTICS,ROBOTICS_ALT) and code in ROBOTS:
        model,module=ROBOTS[code]
        if code not in record.get("pageSkus",{}).get("7",[]) or not re.match(r"^reComputer Robotics "+model+r"\s*[-–]",name,re.I):return []
        package([("Jetson "+module+" module",1),("Seeed Carrier Board (reComputer Robotics J401)",1),
                 ("Aluminum Case and Heatsink with Fan",1),("XT30 to DC cable",1),("USB Cable; Type A to Type C",1),("User Manual",1)],2)
        fact("inbox","128GB NVMe SSD",66,quantity="1",sku="112990226",quantitySource=url+"#page=2")
        for page,options in ROBOT_OPTIONS.items():
            for part,title in options:fact("accessory",title,page,sku=part)
        fact("exclusion","Wall-mounting panel",65)
    elif url==INDUSTRIAL and code in INDUSTRIAL_MODELS and re.match(r"^reComputer Industrial "+INDUSTRIAL_MODELS[code]+r"\b",name,re.I):
        package([("reComputer Industrial",1),("Mounting bracket",2),("DIN rail bracket",1),("Bracket screw",4),
                 ("16-pin terminal block for DIO",1),("19V power adapter",1),("2-pin terminal block power connector",1)],1)
        fact("exclusion","AC power cord",1)
        optional(["EC25EUXGA-MINIPCIE 4G module","EC20CEHCLG-MINIPCIE 4G module","SIM8202G-M2 5G module",
                  "WM1303 LoRaWAN gateway module (SPI, EU868)","TPM2.0 module with Infineon SLB9670","BL-M8723DU1 Wi-Fi/Bluetooth module"],18,True)
    elif url in (NVR,NVR_BRIEF) and code in NVR_MODELS and re.match(r"^reServer Industrial "+NVR_MODELS[code]+r"\b",name,re.I):
        identity_page="3" if url==NVR else "1"
        if code not in record.get("pageSkus",{}).get(identity_page,[]):return []
        page=1 if url==NVR else 2
        package([("reServer Industrial",1),("DIN rail bracket",1),("Bracket screw",10),("16-pin terminal block for DIO",1),
                 ("24V/5A power adapter",1),("2-pin terminal block power connector",1)],page)
        fact("exclusion","AC power cord",page)
        if url==NVR:optional(["EC25EUXGA-MINIPCIE module (GPS / 4G)","EC20CEHCLG-MINIPCIE 4G module","SIM8202G-M2 5G module",
                              "Wio-WM1302 LoRaWAN gateway module (SPI, US915-M)","TPM2.0 module with Infineon SLB9670"],22,True)
    elif url==J401B and code in B_MODELS and re.match(r"^reComputer "+B_MODELS[code][0]+r"\b",name,re.I):
        package([("Jetson "+B_MODELS[code][1]+" module",1),("Seeed carrier board (reComputer J401B)",1),("128GB NVMe SSD",1),
                 ("Aluminum case and heatsink with fan",1),("DC jack power connector",1)],1)
    elif url==T906 and code=="114110168" and name.startswith("Mini AI Computer T906"):
        package([("Mini AI Computer T906",1),("19V power adapter",1),("Mounting bracket",1),("Type-C cable",1),("Power adapter cable",1)],16,"sku")
        fact("exclusion","AC power cord",16,"sku")
    elif url==PLANT and code=="110060130" and name.startswith("Grove Smart Plant Care Kit"):
        package([(title,1) for title in ("Grove - Temp & Humidity Sensor","Grove - Sunlight Sensor V1.0","Grove - Water Flow Sensor",
                 "Grove - Moisture Sensor","Grove - Encoder","Grove - OLED Display 1.12″","Grove - Button","Grove - Relay",
                 "12V DC water pump","12V power connector","Base Shield V2","Manual")],1,"sku")
    elif url==R1_FLYER:
        printed_r10={"113991314","113991274","113991294","113991295"}
        printed_r11={"113991334","113991374","113991375"}
        if not ((code in printed_r10 and name.startswith("reComputer R10")) or (code in printed_r11 and name.startswith("reComputer R11"))):return []
        for option in product.get("accessories",[]):
            part=option.get("sku")
            if part not in FLYER_ACCESSORIES or (part=="110991925" and code in printed_r11):continue
            fact("accessory",option.get("storeName") or option["name"],3,sku=part,soldSeparately=True)
    elif url==BEAGLE and code=="102991698" and re.sub("[^a-z0-9]","",name.casefold()).startswith("beaglevahead"):
        for text,qty in product.get("parts",[]):
            if re.fullmatch(r"\s*[x×]?\s*1\s*",str(qty),re.I) and (re.search(r"antenna",text,re.I) or re.search(r"micro\s*usb.*cable",text,re.I)):
                fact("inbox",text,2,"sku",quantity="1",storeProductSource=product.get("partSource") or product.get("url",""))
        fact("modelSpec","RAM",2,"sku",value="4GB LPDDR4X (2 × 2GB)")
        fact("modelSpec","Storage",2,"sku",value="16GB eMMC")
    return rows


def document_conflicts(url,product,record,catalog):
    if url==QSCOUT and product["sku"]=="110090181" and product.get("name","").startswith("Q-Scout Robot Building Kit") and reviewed_edition(url,record):
        tech=product.get("referenceSections",{}).get("certification_info_tech",{})
        values={r[0]:r[1] for table in tech.get("tables",[]) for r in table.get("rows",[]) if len(r)==2}
        checks=(("Microcontroller","Qmind (Arduino Uno)","Qmind plus main control board",3),
                ("Motor","hobby motor (blue)","520 encoder motor",3),
                ("Types of parts","24","45 numbered part types",4),
                ("Total parts quantity","65","Screws and nuts alone total 90, across numbered rows 32–39",4))
        return [{"name":document,"field":"attachedKitList","catalogName":field+" · "+value,
                 "catalogUrl":tech.get("source") or product.get("url",""),"source":url+"#page="+str(page),
                 **({"otherSources":[url+"#page=3"]} if field=="Total parts quantity" else {})}
                for field,value,document,page in checks if values.get(field)==value]
    if url==JNCRADIO and product["sku"]=="113991034" and reviewed_edition(url,record):
        cable=next((row[0] for row in product.get("parts",[]) if row and re.search(r"\bRG316\b",row[0],re.I)),None)
        if cable:
            return [{"publishedSku":"","name":"20 cm SMA-JJ RG405 cable (×2)","field":"cableModel","catalogName":cable,
                     "catalogUrl":product.get("partSources",{}).get(cable) or product.get("partSource") or product.get("url",""),"source":url+"#page=5"}]
    if url==PLANT and product["sku"]=="110060130" and reviewed_edition(url,record):
        screen=next((r[0] for r in product.get("parts",[]) if r and "OLED" in r[0] and "0.96" in r[0]),None)
        if screen:
            return [{"publishedSku":"","name":"Grove OLED Display 1.12″","field":"displaySize","catalogName":screen,
                     "catalogUrl":product.get("partSources",{}).get(screen) or product.get("partSource") or product.get("url",""),"source":url+"#page=1"}]
    models=SUPER_MODELS if url==SUPER else ROBOTS
    if url not in (ROBOTICS,ROBOTICS_ALT,SUPER) or not reviewed_edition(url,record) or product["sku"] not in models:return []
    if product["sku"] not in record.get("pageSkus",{}).get("7",[]):return []
    conflicts=[]
    for sku,manual in (("114110129","OV5647, 62° FOV camera module"),("114110127","OV5647, 75° FOV camera module")):
        target=catalog.get(sku,{})
        match=re.search(r"OV5647[- ](\d+)",target.get("name",""),re.I)
        if match and match[1]+"°" not in manual:
            conflicts.append({"publishedSku":sku,"name":manual,"field":"fieldOfView","catalogName":target["name"],
                              "catalogUrl":target.get("url",""),"source":url+("#page=65" if url==SUPER else "#page=67")})
    return conflicts
