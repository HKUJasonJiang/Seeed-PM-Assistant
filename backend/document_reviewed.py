"""Model-scoped publisher tables reviewed against the store's exact product."""
from urllib.parse import urlsplit
import re

ATV_URL="https://www.seeedstudio.com/document/pdf/Multi%20Chassis-4WD%20kit%20(ATV%20version).pdf"
TWO_WHEEL_URL="https://www.seeedstudio.com/document/3PA%20InstructionManual%20V1.1.pdf"
RESCUE_URL="https://www.seeedstudio.com/document/pdf/Multi%20Chassis%20Tank%20(Rescue%20Platform)%20Instruction%20manual.pdf"
BATTERY_BOM="https://www.seeedstudio.com/document/pdf/270019001.pdf"
DSO_MANUAL="https://files.seeedstudio.com/wiki/DSO_Nano/res/DSO%20Nano%20v2%20Manual.pdf"
DSO_REPO_MANUAL="https://github.com/SeeedDocument/DSO_Nano/raw/master/res/DSO%20Nano%20v2%20Manual.pdf"
WIO_MANUAL="https://files.seeedstudio.com/wiki/Wio-Terminal/res/Wio-Terminal-User-Manual.pdf"
R1000_FLYER="https://files.seeedstudio.com/wiki/reComputer-R1000/reComputer_flyer.pdf"
FLYER_ACCESSORIES={"114992969","114993268","114992991","114992628","110061501","114992364",
                   "113991134","113991135","113991174","113991214","113991234","110061502",
                   "110061521","114993114","112990267","112990247","112990246","112990226","110991925","110061505","110061506"}
SENSECAP_V13="https://sensecap-docs.seeed.cc/pdf/SenseCAP%20Product%20User%20Guide(LoRaWAN%20Series)-V1.3.pdf"
A1101_PDF="https://files.seeedstudio.com/wiki/SenseCAP-A1101/SenseCAP_A1101_LoRaWAN_Vision_AI_Sensor_User_Guide_V1.0.2.pdf"
S2100_PDF="https://files.seeedstudio.com/products/SenseCAP/S2100/SenseCAP%20S2100%20LoRaWAN%20Data%20Logger%20User%20Guide.pdf"
J2032_PDF="https://files.seeedstudio.com/products/reServer%20J2032%20datasheet.pdf"
ZIMA_MANUAL="https://files.seeedstudio.com/wiki/zimaboard/ZimaBoard_User_Manual.pdf"
ZIMA_MODELS={"102110678":"216","102110679":"432","102110680":"832"}
J1020_DATASHEET="https://files.seeedstudio.com/wiki/reComputer/reComputer-J1020-datasheet.pdf"
A205E_PC="https://files.seeedstudio.com/products/114110148_A205E%20mini%20pc/A205E_Mini_PC_Datasheet.pdf"
T506S_PC="https://files.seeedstudio.com/wiki/AI_Computer_T506S/Mini_AI_Computer_T506S_datasheet.pdf"
BLIKVM_PCIE="https://files.seeedstudio.com/wiki/BliKvm/PCIe/PCIe-datesheet.pdf"
ECOEYE="https://files.seeedstudio.com/products/101991121/EcoEye%20-%20Embedded%20Vision%20Camera%20datasheet.pdf"
JETSON_BOX={
    A205E_PC:("114110148","A205E Mini PC",13,3,[("A205E Mini PC","1"),("Antenna","2"),("Power adapter (without power cord)","1")]),
    T506S_PC:("114110167","Mini AI Computer T506S",16,16,[("Mini AI Computer T506S","1"),("DIO extension plugs","1"),
        ("Mounting bracket","1"),("19V power adapter (without power cord)","1"),("Power adapter cable","1")]),
}
FULL_KITS={
    A1101_PDF:("101990962",7,"sensecap a1101",[("Sensor node",1),("Bracket",1),("Quick start guide",1),("KA4 × 20 mm self-drilling screw",4)]),
    S2100_PDF:("114992872",6,"sensecap s2100",[("Data logger",1),("Bracket",1),("Quick start guide",1),("KA4 × 20 mm self-drilling screw",4)]),
    J2032_PDF:("110061403",3,"reserver j2032",[("reServer J2032",1),("12V/5A power adapter (without power cord)",1),("User manual",1),("Screwdriver",1)]),
}
CORD_EXCLUDED={
    "https://files.seeedstudio.com/products/102110774_A205E%20carrier%20board/A205E%20carrier%20board%20Datasheet.pdf":("102110774","a205e"),
    "https://files.seeedstudio.com/products/114110147_A203MiniPC/A203%20Mini%20PC%20Datasheet.pdf":("114110147","a203"),
    J2032_PDF:("110061403","reserver j2032")
}

# Review decisions refer to a specific publication. A replacement edition at
# the same URL can move or change a packing table while keeping its page count.
VISUAL_DIGESTS={
    ECOEYE:"ae8c895703e4f078421820e87ce07a307dc6ed144cecbc01964e41a288006c51",
    A205E_PC:"67b393750065f0e72137e7e03559a8bdd8a80e9f8137c4b951fc08edd3758d12",
    T506S_PC:"2a667fcbc7ad9d22608760bd302c3d8e461162855d98ca52c9f3d43c20e82205",
    BLIKVM_PCIE:"de489f1fdfd0f0e7590ceb433da3686280efbddacade864872519b29d0673bf7",
    ZIMA_MANUAL:"8f7dda20b2d89f38d9976ba815eaaabcd4566d8ba933df8d03f2ca9c97160f43",
    J1020_DATASHEET:"706b6794c88cac7d3b50815e8bdd7dd1b43cd3aa12da94c216c59cef8e32cdb5",
    WIO_MANUAL:"1e4d0dc36a4d5fca665ca7ed5a71bbed45c41b4d8e39159eb65075915b528bce",
    R1000_FLYER:"9968783680e1dec42837078f4e8e05f5720837ebb0601ff0da483e1dbb42a2e9",
    DSO_MANUAL:"503a32545fc6d1feeae0e677a5f29e14a3825c05cfffe692977136ac2e486f2a",
    DSO_REPO_MANUAL:"503a32545fc6d1feeae0e677a5f29e14a3825c05cfffe692977136ac2e486f2a",
    BATTERY_BOM:"91ed07dbd0ca4dcdf3fc5f2f1250ba4315bc3573c98918cccbead7bc6617eeb7",
    SENSECAP_V13:"9943b7cdfade5b027cf90aa7f7c0117c2971784ebb1eb9168cb47c786b20be47",
    A1101_PDF:"b146c360deda0df47ed96709a6212949d2a8fd3d168407a0bac22bb1a96b5096",
    S2100_PDF:"d2ba2078c794171e0964bc34ef54823c01ac2f21e61839f53bb4f1613b35d2ec",
    J2032_PDF:"293c3c0f05e28bdaa584a428045cd8cc94b45b7bb6b49dc9f62bff241ed35901",
    ATV_URL:"30fe3f37b14749c1666400f5c7846d54dc682a92524e3235934299490e9c0075",
    TWO_WHEEL_URL:"dff97c2f83afc974a7508879525b58bbefcee5b369431b1fa10eb42e955f24d3",
    RESCUE_URL:"ecd17fe134359a8eaac84be391acd0e504a9b14b6aa430b4a1080aa0000ae7b9",
    "https://files.seeedstudio.com/products/102110774_A205E%20carrier%20board/A205E%20carrier%20board%20Datasheet.pdf":
        "20d93efb042daad59ecac781443da3bc4288bab982bfc0caeacf799a90817c85",
    "https://files.seeedstudio.com/products/114110147_A203MiniPC/A203%20Mini%20PC%20Datasheet.pdf":
        "3db1657243e00fc45d6bcfa3971a63bf56f346e9104d62e715d4cd4909f8436d",
}


def reviewed_current(url,record):
    return url in VISUAL_DIGESTS and record.get("sha256")==VISUAL_DIGESTS[url]


def checked_wiki_rows(url,product,record,products):
    """Inspect only the named table/edition and the product identified by the Wiki."""
    targets={
        "4WD_Mecanum_Wheel_Robot_Kit_Series":("110070012","4WD Mecanum Wheel Robot Kit"),
        "Bracket_for_Infrared_Proximity_Sensor":("110060011","Bracket for Infrared Proximity Sensor"),
        "Capacitance_Meter_Kit":("405010003","Capacitance Meter Kit"),
        "Grove-Beginner-Kit-For-Arduino":("110061162","Grove Beginner Kit for Arduino"),
        "LoRa_LoRaWan_Gateway_Kit":("110060622","LoRa LoRaWAN Gateway - 868MHz Kit with Raspberry Pi 3"),
        "Seeeduino_Stalker_V3.1":("102010070","Seeeduino Stalker V3.1"),
        "XIAO-Kit-Courses":("110010044","Seeed Studio XIAO Starter Kit"),
        "Grove_Smart_Plant_Care_Kit":("110060130","Grove Smart Plant Care Kit for Arduino"),
    }
    slug=url.rstrip("/").rsplit("/",1)[-1]
    if slug not in targets or url!="https://wiki.seeedstudio.com/"+slug+"/":return []
    code,title=targets[slug]
    if product["sku"]!=code or not product.get("name","").startswith(title):return []
    source=record.get("markdownSource","")
    revision="https://github.com/Seeed-Studio/wiki-documents/blob/c9321cc04d695f7b89ed273908558854fe00ab50/sites/en/docs/"
    if not source.startswith(revision) or not source.endswith("/"+slug+".md"):return []
    if code not in {*record.get("purchaseSkus",[]),*record.get("declaredSkus",[])}:return []
    facts=[]
    def add(kind,name,line,**kw):
        facts.append({"kind":kind,"name":name,"source":source+"#L"+str(line),"scope":"sku","basis":"reviewed_wiki_product_table",
                      "modelSource":product.get("url",""),**kw})
    if code=="110060011":
        for line,name,qty in [(43,"IR sensor bracket (10034R0)",1),(44,"Angle mounting bracket (10034R0)",1),
                              (45,"Plastic rivet, 3 × 5.5 mm",2),(46,"Plastic rivet, 2 × 4.8 mm",10),(47,"Self-locking tie, 2 × 56 mm",2)]:
            add("inbox",name,line,quantity=str(qty))
        harness=products.get("110060009",{})
        if harness.get("name")=="Starter Bundle Harness" and harness.get("url","").endswith("-p-906.html"):
            add("accessory","Starter Bundle Harness, 20 mm hole spacing",20,sku="110060009",storeProductSource=harness["url"])
    elif code=="405010003":
        add("exclusion","Power supply",44)
        add("inbox","Capacitance-meter kit components (not itemized)",44,quantity="")
        add("inbox","Schematic",45,quantity="")
        add("inbox","Manual",46,quantity="")
    elif code=="110061162":
        rows={n:(q,line) for n,q,line in [
            ("Temperature & Humidity Sensors",1,95),("3-Axis Accelerometers",1,96),("Air Pressure",1,97),("Light Sensor",1,98),
            ("Sound Sensor",1,99),("Rotary Potentiometer",1,101),("Button",1,102),("LED",1,104),("Buzzer",1,105),
            ("OLED Display",1,107),("Grove Cables",6,108)]}
        for name,qty in product.get("parts",[]):
            if name in rows and str(qty).strip("×xX ")==str(rows[name][0]):
                add("inbox",name,rows[name][1],quantity=str(rows[name][0]))
        # The Wiki differentiates a USB cable revision; its two editions must
        # not turn into two cables included in one order.
    elif code=="110010044":
        image="https://media-cdn.seeedstudio.com/media/catalog/product/cache/bb49d3ec4ee05b6f018e93f896b8a25d/s/e/seeed_studio_xiao_starter_kit_-_all_seeed_studio_xiao_series_deve_after_1_.jpg"
        observed="data/jpg/6348d0f00fd20f5b4c32a8137a66362796ffa23ae64153df9db6449fc4db95ee.jpg"
        if (product.get("image")==observed and product.get("imageUrl","").endswith(image.split("/s/e/")[-1])
                and any(n=="Grove Cable" and str(q).strip("x× ")=="7" for n,q in product.get("parts",[]))):
            add("inbox","Grove Cable",43,quantity="7",publicationImage=image,storeProductSource=product.get("partSource") or product["url"])
    elif code=="110060130":
        # The Wiki explicitly says the kit includes these modules, without
        # giving unit counts. Cross-check the listed components in this SKU.
        verified={"Grove - Base Shield":126,"Grove - Temp & Humi Sensor":109,"Grove - Moisture Sensor":114,
                  "Grove - Sunlight Sensor":111,"Grove - Encoder":115,"Grove - Button":119,"Grove - Relay":120,
                  "Grove - Water Flow Sensor":112,"12V Water Pump":122}
        for name,_ in product.get("parts",[]):
            if name in verified:add("inbox",name,verified[name],quantity="")
    elif code=="102010070":
        # The guide's GET ONE NOW row pairs each named setup item with its
        # catalogue ID, then explicitly excludes the three from the box.
        for sku,store_id,title in [("103990023","688","UartSBee V4"),("321010005","252","Mini USB cable 100cm"),
                                   ("110990077","128","6 pin dual-female jumper wire - 300mm (5 PCs pack)")]:
            item=products.get(sku,{})
            if item.get("name")==title and item.get("url","").endswith("-p-"+store_id+".html"):
                add("accessory",title,133,sku=sku,storeProductSource=item["url"],notIncludedSource=source+"#L136")
    elif code=="110060622":
        # The guide's line 35 names the illustrated 868 MHz version. The
        # separate 915 MHz product link is not evidence for the 868 MHz box.
        for line,name in [(87,"Raspberry Pi 3"),(92,"Gateway module RHF0M301 – 868"),(97,"PRI 2 Bridge RHF4T002"),
                          (102,"Seeeduino LoRaWAN with GPS"),(107,"USB to UART Adapter"),(112,"16GB Micro SD Card – Class 10 (guide revision)"),
                          (117,"0dBi Rubber Duck Antenna"),(122,"5V/2.1A American Standard Adapter with Micro USB Connector"),
                          (127,"Micro USB Cable 20cm"),(132,"Micro USB Cable 100cm"),(137,"RJ45 Ethernet Cable 200cm"),(142,"JST2.0 cable 10cm")]:
            add("inbox",name,line,quantity="1")
    else:
        rows=[("Chassis",1),("Upper Deck",1),("Battery Cover",1),("Left Mecanum Wheel Φ60mm H32mm",2),
              ("Right Mecanum Wheel Φ60mm H32mm",2),("DC Motor-25 GA 370 Standard Version",4),
              ("Motor Support for DC Motor-25 Series",4),("Shaft Connector",4),("Set Screw M3×5",8),
              ("Screw, Spring Lock Washer and Plain Washer assemblies M4×18",4),("Screw, Spring Lock Washer and Plain Washer assemblies M2×8",20),
              ("Cross Recessed Pan Head Screw M3×8",26),("Cross Recessed Pan Head Screw with Washer M3×8",16),("Hexagon Nut M3",16),
              ("Hexagon Distance Holder M3×40",5),("Hexagon Distance Holder M3×10",4),("Hexagon Distance Holder M2×15",4),("Hexagon Distance Holder M2×10",6)]
        store_box={(n,str(q).strip("×xX ")) for n,q in product.get("parts",[])}
        if not all((n,str(q)) in store_box for n,q in rows):return []
        # The SKU's entire store box matches the Basic Version. RF/BLE editions
        # and the separate wheel-only tables are intentionally not combined.
        for i,(name,q) in enumerate(rows):add("inbox",name,242+7*i,quantity=str(q))
        for option in ("BLE remote-control module","RF remote-control module"):add("accessory",option,17,namedAccessory=True)
    return facts


def checked_wiki_conflicts(url,product,record):
    applicable=training_scope(url,product,record)
    if applicable:
        product_url=product.get("url","")
        note="The Motor Kit does not include 3D-printed parts and camera"
        if note.casefold() in product.get("summary","").casefold():
            return [{"publishedSku":"","field":"guidePackageScope","name":"Training setup describes one included camera and one additional camera",
                     "catalogName":note,"catalogUrl":product_url+"#:~:text=The%20Motor%20Kit%20does%20not%20include",
                     "source":record["markdownSource"]+"#L66"}]
    if (url=="https://wiki.seeedstudio.com/Grove_Smart_Plant_Care_Kit/" and product["sku"]=="110060130"
            and product["sku"] in record.get("declaredSkus",[]) and product.get("name","").startswith("Grove Smart Plant Care Kit")):
        source=record.get("markdownSource","")
        screen=next((r[0] for r in product.get("parts",[]) if r and "OLED" in r[0] and "0.96" in r[0]),None)
        if screen and re.fullmatch(r"https://github\.com/Seeed-Studio/wiki-documents/blob/c9321cc04d695f7b89ed273908558854fe00ab50/sites/en/docs/.+/Grove_Smart_Plant_Care_Kit\.md",source):
            return [{"publishedSku":"","name":"Grove OLED Display 1.12″","field":"displaySize","catalogName":screen,
                     "catalogUrl":product.get("partSources",{}).get(screen) or product.get("partSource") or product.get("url",""),"source":source+"#L117"}]
    if (url!="https://wiki.seeedstudio.com/LoRa_LoRaWan_Gateway_Kit/" or product["sku"]!="110060622"
            or "868MHz" not in product.get("name","")):return []
    source=record.get("markdownSource","")
    if "c9321cc04d695f7b89ed273908558854fe00ab50" not in source or not source.endswith("/LoRa_LoRaWan_Gateway_Kit.md"):return []
    values=[]
    for pattern,field,label,line in [(r"8GB Micro SD","storageCapacity","16GB Micro SD card (guide revision)",112),
                                     (r"RJ45 Ethernet Cable 100cm","cableLength","RJ45 Ethernet cable, 200 cm",137)]:
        found=next((n for n,q in product.get("parts",[]) if re.search(pattern,n,re.I)),None)
        if found:
            values.append({"publishedSku":"","field":field,"name":label,"catalogName":found,
                           "catalogUrl":product.get("partSources",{}).get(found) or product.get("partSource") or product.get("url",""),
                           "source":source+"#L"+str(line)})
    return values


def training_scope(url,product,record):
    source=record.get("markdownSource","")
    return (url=="https://wiki.seeedstudio.com/sensecraft_robotics_so_arm101/" and product["sku"]=="114993667"
            and product.get("name","").startswith("SO-ARM101 Pro Servo Motor Kit") and product["sku"] in record.get("purchaseSkus",[])
            and "application" in record.get("sourceScopes",[]) and source.endswith("/Cloud_Chain/SenseCraft_Robotics/guides/sensecraft_robotics_so_arm101.md")
            and "/Seeed-Studio/wiki-documents/blob/c9321cc04d695f7b89ed273908558854fe00ab50/sites/en/docs/" in source)


def supplementary_wiki_scope(url,product,record):
    source=record.get("markdownSource","")
    repo="https://github.com/Seeed-Studio/wiki-documents/blob/c9321cc04d695f7b89ed273908558854fe00ab50/sites/en/docs/"
    if training_scope(url,product,record):
        return "application",[(50,"example_configuration","Arms and cables used in the training setup",source+"#L50"),
                              (61,"example_configuration","Cameras and other shared training materials",source+"#L61")]
    if (url in {"https://wiki.seeedstudio.com/Grove_System/","https://wiki.seeedstudio.com/Grove_System","https://www.seeedstudio.com/wiki/Grove_System"}
            and record.get("title")=="Grove Ecosystem Introduction" and (
                source==repo+"Sensor/Grove/Grove_System.md" or record.get("publishedRedirect","").rstrip("/")=="https://wiki.seeedstudio.com/Grove_System")):
        return "ecosystem",[(72,"ecosystem","Grove ecosystem accessories",repo+"Sensor/Grove/Grove_System.md#L72")]
    if (url.rstrip("/")=="https://wiki.seeedstudio.com/Bluetooth_Bee" and product["sku"]=="113050001"
            and "BC04" in product.get("name","") and source==repo+"Seeed_Elderly/Bee/Bluetooth_Bee.md"):
        return "component_guide",[(619,"assembly_components","Bare PCB and radio module used in the Bluetooth Bee",source+"#L619")]
    return None


def exact_model_rows(url,product,record,products):
    if not reviewed_current(url,record):return []
    title=product.get("name","").casefold()
    rows=[]
    if url in CORD_EXCLUDED:
        sku,model=CORD_EXCLUDED[url]
        if product["sku"]==sku and title.startswith(model) and record.get("pages",0)>=3:
            rows.append({"kind":"exclusion","name":"AC power cord","source":url+"#page=3","scope":"sku","basis":"model_packing_list"})
    if url not in FULL_KITS:return rows
    sku,page,model,parts=FULL_KITS[url]
    if product["sku"]!=sku or not title.startswith(model) or record.get("pages",0)<page:return []
    source=url+"#page="+str(page)
    rows.extend({"kind":"inbox","name":n,"quantity":str(q),"source":source,"scope":"sku","basis":"reviewed_model_packing_table"} for n,q in parts)
    if url==S2100_PDF:
        option={"kind":"accessory","name":"Junction box accessory kit","namedAccessory":True,"source":source,"scope":"sku","basis":"guide_optional_kit"}
        related=products.get("114992988",{})
        if "junction box kit" in related.get("name","").lower() and "s2100 data logger" in related["name"].lower() and related.get("url"):
            option.update(sku="114992988",storeProductSource=related["url"],basis="optional_kit_and_matching_store_model")
        rows.extend([option,{"kind":"exclusion","name":"Junction box accessory kit","source":source,"scope":"sku","basis":"separately_ordered_option"}])
    if url==J2032_PDF and record.get("pages",0)>=14:
        optional_source=url+"#page=14"
        for name in ("Quectel EC25 / EC20 4G module","SIMCom SIM8202G 5G module","WM1302 LoRaWAN gateway module (USB/SPI, US/EU)"):
            option={"kind":"accessory","name":name,"namedAccessory":True,"source":optional_source,"scope":"sku",
                    "basis":"named_model_option_excluded_from_package","notIncludedSource":optional_source}
            # Only the USB EU variant is offered on this exact machine's
            # storefront. Other revisions or regional SKUs stay unspecified.
            if name.startswith("WM1302"):
                for offered in product.get("accessories",[]):
                    item=products.get(offered.get("sku"),{})
                    if (offered.get("type")=="商品页 Also Add 加购项" and item.get("sku")=="114992628"
                            and "wm1302" in item.get("name","").lower() and "(usb)" in item["name"].lower() and "EU868" in item["name"]):
                        option.update(sku=item["sku"],storeProductSource=item.get("url",""))
                        break
            rows.append(option)
    return rows


def other_visual_rows(url,product,record):
    if not reviewed_current(url,record):return []
    if url==ECOEYE:
        if record.get("pages")!=3 or product["sku"]!="101991121" or not product.get("name","").startswith("EcoEye: OpenMV H7+ Camera"):return []
        source=url+"#page=3"
        names=["Fully assembled EcoEye camera (with the standard 2.8mm lens on it, batteries and SD card not included)",
               "USB-C data cable","1.8mm lens","6.0mm lens","12.0mm lens"]
        facts=[{"kind":"inbox","name":n,"quantity":"1","source":source,"scope":"sku","basis":"model_datasheet_part_list"} for n in names]
        facts.append({"kind":"exclusion","name":"Batteries and SD card","source":source,"scope":"sku","basis":"model_datasheet_part_list"})
        facts.append({"kind":"expansion","name":"Multi-pin connector for a 12V solar panel, I2C and analog sensors","source":source,
                      "scope":"sku","basis":"EcoEye H7+ camera datasheet"})
        return facts
    if url in JETSON_BOX:
        sku,model,pages,page,items=JETSON_BOX[url]
        if product["sku"]!=sku or not product.get("name","").startswith(model) or record.get("pages")!=pages:return []
        source=url+"#page="+str(page)
        return [{"kind":"inbox","name":name,"quantity":qty,"source":source,"scope":"sku","basis":"model_datasheet_part_list"} for name,qty in items]+[
            {"kind":"exclusion","name":"AC power cord","source":source,"scope":"sku","basis":"model_datasheet_part_list"}]
    if url==BLIKVM_PCIE:
        if (product["sku"]!="114110230" or record.get("pages")!=6 or
                not product.get("name","").startswith("BliKVM Plug-n-Play PCIe")):return []
        first=["BLIKVM PCIe add-in card","CM4 002000","Cooling fan","OLED display","USB to TTL module","HDMI pass-through EDID emulator",
               "VGA-HDMI module","32G Micro SD card","HDMI cable 0.5m","HDMI Coupler","Network cable 1m","USB-A to USB-C cable 1m",
               "Dupont USB cable 0.4m","WiFi antenna"]
        last=["Dupont Cables 8pin Male to Male 40cm","Dupont Cables 8pin Male to Female 40cm","Metal heatsink","Phillips screwdriver","Cross Wrench Sleeve"]
        return [{"kind":"inbox","name":n,"quantity":"2" if n=="USB-A to USB-C cable 1m" else "1","source":url+"#page="+str(page),
                 "scope":"sku","basis":"published_plug_and_play_column"} for page,names in ((5,first),(6,last)) for n in names]
    if (url==J1020_DATASHEET and product["sku"]=="110061361" and record.get("pages")==23
            and re.match(r"^reComputer J1020\b",product.get("name",""),re.I)):
        names=["Jetson Nano","Seeed reference carrier board","Passive aluminium heatsink","Aluminium case (black)",
               "12V/2A power adapter (with 5 interchangeable adapter plugs)"]
        return [{"kind":"inbox","name":n,"quantity":"1","source":url+"#page=1","scope":"sku","basis":"model_datasheet_part_list"} for n in names]
    if url==ZIMA_MANUAL:
        model=ZIMA_MODELS.get(product["sku"])
        if not model or record.get("pages")!=8 or not product.get("name","").startswith("ZimaBoard "+model+"-X86 Single Board Server"):return []
        return [{"kind":"inbox","name":n,"quantity":q,"source":url+"#page=3","modelSource":url+"#page=1",
                 "scope":"family","family":"ZMB-216 / ZMB-432 / ZMB-832","basis":"shared_model_packing_illustration"}
                for n,q in (("ZimaBoard","1"),("SATA cable","1"),("User manual","1"),("Sticker","2"))]
    if url==WIO_MANUAL and product["sku"]=="102991299" and product.get("name","").lower().startswith("wio terminal: atsamd51") and record.get("pages",0)>=2:
        return [{"kind":"inbox","name":name,"source":url+"#page=2","scope":"sku","basis":"visual_box_panel_no_quantities"}
                for name in ("Wio Terminal","Short USB Type-C cable","User manual")]
    if url==R1000_FLYER and record.get("pages",0)>=3 and any(w.get("scope","").upper()=="R1000" for w in product.get("wikiEvidence",[])):
        return [{"kind":"accessory","sku":part["sku"],"name":part.get("storeName") or part["name"],
                 "source":url+"#page=3","scope":"family","basis":"R1000 flyer column and verified accessory SKU"}
                for part in product.get("accessories",[]) if part.get("sku") in FLYER_ACCESSORIES]
    return []


def sensecap_common_box(product,record):
    # Section 3.1.2 explicitly calls these the common contents of the sensor
    # nodes. Region-specific radios and installation extras are separate.
    if not reviewed_current(SENSECAP_V13,record) or record.get("pages")!=50 or not re.match(r"^SenseCAP Wireless (?:Soil Moisture and Temperature|Air Temperature and Humidity|Light Intensity|CO2|Barometric Pressure) Sensor\s*-\s*LoRaWAN",product.get("name",""),re.I):
        return []
    items=[("Sensor",1),("Bracket",1),("M4 self-drilling screw",4),("M3 self-drilling screw",2)]
    return [{"kind":"inbox","name":name,"quantity":str(qty),"source":SENSECAP_V13+"#page=11","scope":"family","basis":"SenseCAP LoRaWAN sensor node common package, section 3.1.2"} for name,qty in items]

# These official Part List sections describe the actual supplied kit. The
# Micro:bit guide also has two demonstration shopping lists; only its first
# table is approved. Atom-X's following subsection describes the internal
# robot assembly and must not be counted again as loose items.
REVIEWED_WIKI_BOX={
    "107020007":("Grove-Recorder_v2.0","parts-list",0,0),
    "110060762":("Grove_Inventor_Kit_for_microbit","parts-list",0,0),
    "113110064":("wio_sx1262_and_xiao_esp32s3_kit_with_3dprinted_enclosure_introduction_and_assembly_guide","part-list",91,92),
    "100092737":("atom_x","",62,66),
    "110990086":("Basic_Fastener_Kit","part-list",25,25),
    "110060576":("ESP32_Breakout_Kit","part-list",34,38),
    "106060002":("Sidekick_Basic_Kit_for_TI_LaunchPad","parts-list",28,28),
    "103100002":("Breakout_for_LinkIt_Smart_7688","parts-list",91,91),
    "110992164":("grove_barometer_sensor_spa06_003","part-list",174,174)
}
REVIEWED_WIKI_BOX.update({
    "110020108":("Grove_Speech_Recognizer_Kit_for_Arduino","part-list",36,46),
    "103030034":("BeagleBone_Green_HDMI_Cape","parts-list",74,74),
    "103030035":("Grove_Base_Cape_for_BeagleBone_v2","parts-list",73,73),
    "102010611":("wio_sx1262_with_xiao_esp32s3_kit","part-list",94,97),
    "103990021":("Danger_Shield_Complete_Kits","",69,69),
    "103020031":("Grove_Base_Shield_for_Photon","parts-list",57,57),
    "110010000":("Skeleton_Bot-4WD_hercules_mobile_robotic_platform","",49,49),
    "105990001":("AVR_USB_Programmer","",36,36),
    "101020090":("Grove-Water_Atomization","parts-list",84,86),
    "105020012":("Grove-6-Axis_AccelerometerAndGyroscope","parts-list",95,96),
    "103020030":("Grove-Mouse_Encoder","parts-list",89,90),
    "103030356":("Seeeduino-XIAO-Expansion-Board","part-list",96,96),
    "110020109":("Grove_Starter_kit_for_Arduino_101","parts-list",91,91),
    "110060024":("Grove_Starter_Kit_v3","parts-list",45,63),
    "110020006":("Techbox_Tricks","",48,72),
    "104030047":("Starter_Shield_EN","parts-list",41,91),
})


def is_reviewed_wiki_box(sku,record,row):
    entry=REVIEWED_WIKI_BOX.get(sku)
    if not entry:return False
    official="https://wiki.seeedstudio.com/"+entry[0]+"/"
    if record.get("url")!=official:return False
    source=row["source"]
    if entry[1] and source==official+"#"+entry[1]:return True
    pinned=record.get("markdownSource","")
    if not pinned or "/blob/c9321cc04d695f7b89ed273908558854fe00ab50/" not in pinned:return False
    mark=urlsplit(source).fragment
    if not (source.startswith(pinned+"#L") and mark[1:].isdigit()):return False
    return entry[2]<=int(mark[1:])<=entry[3] or (row.get("tableLine") is not None and entry[2]<=row["tableLine"]<=entry[3])

# A publisher part number is a drawing or assembly identifier, not a Seeed sale SKU.
REVIEWED_TABLES={
    RESCUE_URL:("110990107",1,"Multi Chassis Tank (Rescue Version) Robot Platform",[
        ("","Upper aluminium chassis",1),("","Lower aluminium chassis",1),("","Ø4 Kimi screw",2),("","DC motor",2),
        ("","Track wheel",8),("","Rubber belt",4),("","M3 × 6 hex screw",2),("","M3 × 8 round-head screw",8),
        ("","Hex key (Ø3 / Ø4 as marked)",1),("","Spanner for M2.5 / M4",1),("","Spanner for M2 / M3",1),
        ("","M3 × 25 spacer",4),("","M3 × 8 flat-head screw",8),("","M3 × 35 screw",2),
        ("","M3 × 16 flange screw",2),("","M3 nyloc nut",2),("","Thin M3 washer",10),("","M2.5 × 25 screw",2),
        ("","M2.5 nyloc fastener (position 19)",4),("","M3 nut",4),("","M3 × 8 flange screw",4),
        ("","Ø3 × 10 spacer",2),("","M2.5 × 20 screw",2),("","Ø3 × 28 spacer",2),
        ("","15 × 20 × 1 washer",4),("","Hall sensor holder",2),("","M2.3 × 8 flange tapping screw",6),
        ("","10 × 15 × 4 flange bearing",4),("","5 × AA battery holder",1),("","Screwdriver",1),
        ("","Hall sensor encoder kit",2),("","Ø4 hexagonal connecting piece",2),("","Aluminium bracket",2),
        ("","Long axle",1),("","Ø4 16-tooth synchronizing gear",1),("","Ø4 24-tooth synchronizing gear",1),
        ("","60MXL synchronizing belt",1),("","Hall sensor",2),("","13 kg servo",1),("","M3 × 22 screw",1),
        ("","U-shaped holder",1),("","Ø3 × 12 spacer",1)]),
    ATV_URL:("110990087",1,"Multi Chassis-4WD Robot Kit (ATV version)",[
        ("","Upper aluminium chassis plate",1),("","Lower aluminium chassis plate",1),
        ("","DC motor",4),("","Racing wheel",4),("","M3 × 25 spacer",4),
        ("","M3 × 8 flat-head screw",6),("","M2.5 × 20 screw",4),("","M2.5 × 25 screw",4),
        ("","M3 × 22 flange screw",4),("","M3 × 8 screw",8),("","M2.5 nylon nut",8),
        ("","M3 nut",2),("","5 × AA battery holder",1),("","Spanner for M2.5 / M4",1),
        ("","Spanner for M2 / M3",1),("","Screwdriver",1)]),
    TWO_WHEEL_URL:("110990061",12,"2WD Arduino compatible Mobile platform",[
        ("F0501","Chassis lower plate",1),("F0502","Chassis upper plate",1),
        ("F0503","Sensor mounting grille",1),("F0504","IR sensor mounting bracket",3),
        ("F0505","Caster",1),("M0501","M2.5 × 25 Phillips truss screw",4),
        ("M0502","M2.5 washer",4),("M0503","M2.5 spring washer",4),("M0504","M2.5 nut",4),
        ("M0505","M4 × 8 Phillips truss screw",2),("M0506","M4 nut",2),
        ("M0507","M3 × 6 Phillips flange screw",19),("M0508","M3 nut",19),
        ("M0509","M3 × 5 Phillips countersunk screw",2),("M0510","M6 nut",2),
        ("M0511","M6 special washer",1),("M0512","Power switch",1),("M0513","M8 nut",1),
        ("M0514","M8 spring washer",1),("M0515","Power jack",1),("M0516","M3 × 10 copper pillar",4),
        ("P0501","Wheel",2),("P0502","Motor",2),("P0503","Battery holder",1)])
}


def reviewed_rows(url,product,record):
    if not reviewed_current(url,record):return []
    audit=REVIEWED_TABLES.get(url)
    if not audit or product["sku"]!=audit[0] or product.get("name","").casefold()!=audit[2].casefold():return []
    if (record.get("pages") or 0)<audit[1]:return []
    out=[]
    for number,name,qty in audit[3]:
        row={"kind":"inbox","name":name,"quantity":str(qty),"scope":"sku","basis":"visually_verified_packing_table",
             "source":url+"#page="+str(audit[1])}
        if number:row["partNumber"]=number
        out.append(row)
    return out
