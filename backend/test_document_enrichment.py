"""Regression checks for source scope, archival status, SKU matching and physical pages."""
import copy
import json
from collections import Counter
from pathlib import Path
import unittest
from unittest.mock import patch, mock_open
from . import document_enrichment as scanner
from .document_merge import identity, merge_rows, accepted, edgelogix_facts, candidate_section_links, log_records, write_bundle
from .document_wiki import parse_markdown
from .document_reviewed import ATV_URL,TWO_WHEEL_URL,S2100_PDF,SENSECAP_V13,J2032_PDF,VISUAL_DIGESTS,reviewed_rows,sensecap_common_box,exact_model_rows,checked_wiki_rows,checked_wiki_conflicts
from . import document_product_tables as product_tables
from . import document_variant_tables as variants
from .document_reviewed import ZIMA_MANUAL, ZIMA_MODELS, JETSON_BOX, BLIKVM_PCIE, other_visual_rows
from .document_family_services import explicit_service, COMMITMENT, SERVICE


class DocumentEvidenceTests(unittest.TestCase):
    def test_assembly_screw_use_is_separate_from_the_number_packed(self):
        src=variants.ACRYLIC
        sha,pages=variants.EDITIONS[src]
        rec={"sha256":sha,"pages":pages}
        p={"sku":"110991984","name":"Acrylic Enclosure for reSpeaker Lite","url":"https://www.seeedstudio.com/case.html",
           "parts":[["Phillips Round Head Machine Screws - PM2.0_H6.0mm","4"],["Double-sided Tape (Small Roll)","1"],
                    ["Black Double-sided Adhesive EVA Foam - 16_16_8","2"]]}
        rows,conf=variants.reviewed(src,p,rec)
        self.assertEqual([r["kind"] for r in rows],["modelSpec"])
        self.assertEqual(len(conf),2)
        self.assertEqual(conf[0]["source"],src+"#page=2")
        self.assertIn("uses 6",conf[0]["name"])
        self.assertIn("4 in the store packing list",conf[0]["catalogName"])
        self.assertIn("8 cut strips",rows[0]["value"])
        bundle={**p,"sku":"E24072601","name":"reSpeaker Lite Voice Assistant Kit"}
        self.assertEqual(variants.reviewed(src,bundle,rec),([],[]))
        self.assertEqual(variants.figure_scope(src,bundle,rec)[0],"component_guide")
        self.assertIsNone(variants.figure_scope(src,bundle,{**rec,"sha256":"unreviewed"}))

    def test_odyssey_v2_region_rule_never_overwrites_the_blue_telec_bundle(self):
        src=variants.ODYS[1]
        sha,pages=variants.EDITIONS[src]
        record={"sha256":sha,"pages":pages}
        blue={"sku":"110991825","name":"ODYSSEY Blue J4125 v2 Mini PC(TELEC)","url":"https://www.seeedstudio.com/blue.html",
              "parts":[["International Power Adaptor(12V 2A)","x1"],["Antenna","x2"]]}
        rows,conf=variants.reviewed(src,blue,record)
        self.assertEqual([(r["name"],r["quantity"]) for r in rows],[("Antenna","2")])
        self.assertEqual(conf[0]["source"],src+"#page=2")
        board={"sku":"102110766","name":"ODYSSEY - X86J4125800 v2(TELEC)","parts":[["SATA Cable","1"]]}
        rows,conf=variants.reviewed(src,board,record)
        self.assertEqual([r["kind"] for r in rows],["inbox","exclusion"])
        self.assertFalse(conf)
        self.assertEqual(variants.reviewed(src,{**board,"sku":"110991565"},record),([],[]))
        self.assertEqual(variants.reviewed(src,board,{**record,"sha256":"another edition"}),([],[]))

    def test_pc_packing_tables_are_scoped_to_the_version_and_physical_page(self):
        for url,(sku,title,pages,page,box) in JETSON_BOX.items():
            record={"pages":pages,"sha256":VISUAL_DIGESTS[url]}
            rows=other_visual_rows(url,{"sku":sku,"name":title},record)
            self.assertEqual([(r["name"],r["quantity"]) for r in rows if r["kind"]=="inbox"],box)
            self.assertEqual(rows[-1]["kind"],"exclusion")
            self.assertEqual(rows[-1]["source"],url+"#page="+str(page))
            self.assertFalse(other_visual_rows(url,{"sku":"114110147","name":title},record))
        p={"sku":"114110230","name":"BliKVM Plug-n-Play PCIe","parts":[["USB-A to USB-C cable 1m","1"]]}
        rec={"pages":6,"sha256":VISUAL_DIGESTS[BLIKVM_PCIE]}
        facts=other_visual_rows(BLIKVM_PCIE,p,rec)
        self.assertEqual(len(facts),19)
        self.assertEqual([r["quantity"] for r in facts if r["name"]=="CM4 002000"],["1"])
        self.assertEqual(len([r for r in facts if r["source"].endswith("#page=6")]),5)
        merge_rows(p,[{**row,"documentUrl":BLIKVM_PCIE} for row in facts],{})
        self.assertEqual(p["partConflicts"][0]["documentQuantity"],"2")
        self.assertEqual(p["parts"],[["USB-A to USB-C cable 1m","1"]])
        self.assertFalse(other_visual_rows(BLIKVM_PCIE,{**p,"name":"BliKVM bare PCIe card"},rec))

    def test_zima_shared_illustration_retains_separate_store_box(self):
        record={"pages":8,"sha256":VISUAL_DIGESTS[ZIMA_MANUAL]}
        for sku,model in ZIMA_MODELS.items():
            store=[["Zima Board "+model+"-X86","x1"],["12V 3A power adapter","x1"],["Compatible data circuit cable","x1"]]
            p={"sku":sku,"name":"ZimaBoard "+model+"-X86 Single Board Server","parts":copy.deepcopy(store),"url":"https://www.seeedstudio.com/board.html"}
            facts=other_visual_rows(ZIMA_MANUAL,p,record)
            self.assertEqual(len(facts),4)
            merge_rows(p,[{**row,"documentUrl":ZIMA_MANUAL} for row in facts],{})
            self.assertEqual(p["parts"],store)
            secondary=p["alternatePackingLists"][0]
            self.assertEqual(secondary["scope"],"family")
            self.assertEqual(secondary["source"],ZIMA_MANUAL+"#page=3")
            self.assertEqual(secondary["parts"],[["ZimaBoard","1"],["SATA cable","1"],["User manual","1"],["Sticker","2"]])
            self.assertFalse(other_visual_rows(ZIMA_MANUAL,{**p,"name":"ZimaBoard 999-X86 Single Board Server"},record))
            self.assertFalse(other_visual_rows(ZIMA_MANUAL,p,{**record,"sha256":"different release"}))

    def test_original_odyssey_power_adapter_is_specific_to_the_variant(self):
        source=product_tables.ODYSSEY_BLUE
        rec={"sha256":product_tables.DIGESTS[source],"pages":1}
        standard={"sku":"110991564","name":"Odyssey Blue: J4125 128GB Win10 PC","url":"https://www.seeedstudio.com/pc.html",
                  "parts":[["ODYSSEY - X86J4125","1"],["User Manual","1"],["International Power Adapter",""]]}
        telec={**standard,"sku":"110991565","name":"Odyssey Blue: J4125 128GB (TELEC)","parts":standard["parts"][:2]}
        later={**standard,"sku":"110991825","name":"ODYSSEY Blue J4125 v2 (TELEC)"}
        shop_rows=product_tables.source_rows(source,standard,rec)
        merge_rows(standard,shop_rows,{})
        self.assertIn(["International Power Adapter","1"],standard["parts"])
        self.assertEqual(standard["partQuantitySources"]["International Power Adapter"],source+"#page=1")
        self.assertIn("Power adapter (TELEC version)",[x["name"] for x in product_tables.source_rows(source,telec,rec) if x["kind"]=="exclusion"])
        self.assertEqual(product_tables.source_rows(source,later,rec),[])

    def test_training_camera_and_motor_only_sku_are_distinguished(self):
        url="https://wiki.seeedstudio.com/sensecraft_robotics_so_arm101/"
        product={"sku":"114993667","name":"SO-ARM101 Pro Servo Motor Kit – LeRobot Compatible",
                 "summary":"Note: The Motor Kit does not include 3D-printed parts and camera.","url":"https://www.seeedstudio.com/kit.html"}
        doc={"sourceScopes":["application"],"purchaseSkus":["114993667"],"markdownSource":
             "https://github.com/Seeed-Studio/wiki-documents/blob/c9321cc04d695f7b89ed273908558854fe00ab50/sites/en/docs/Cloud_Chain/SenseCraft_Robotics/guides/sensecraft_robotics_so_arm101.md"}
        match=checked_wiki_conflicts(url,product,doc)
        self.assertEqual(match[0]["field"],"guidePackageScope")
        self.assertTrue(match[0]["source"].endswith("#L66"))
        self.assertFalse(checked_wiki_rows(url,product,doc,{}))
        self.assertFalse(checked_wiki_conflicts(url,{**product,"sku":"114993666"},doc))

    def test_pdf_example_and_component_assembly_have_reviewable_pages_only(self):
        examples=[
            (product_tables.INVENTOR_GUIDE,"110060762",["example_configuration"]*12,5),
            (product_tables.WEATHER_SENSOR_V2,"E23010807",["component_guide"],8),
            (product_tables.NOSE_BOARD,"110990217",["assembly_components"],8),
            (product_tables.LORA_CERT,"102010129",["certification"],2),
        ]
        for url,sku,kinds,first in examples:
            record={"sha256":product_tables.DIGESTS[url]}
            _,sections=product_tables.sections_outside_product_box(url,record,{"sku":sku})
            self.assertEqual([s[1] for s in sections],kinds)
            self.assertEqual(sections[0][0],first)
            self.assertIsNone(product_tables.sections_outside_product_box(url,{"sha256":"new"},{"sku":sku}))

    def test_scout_attachment_technical_discrepancies_do_not_become_in_box_items(self):
        guide=product_tables.QSCOUT
        product={"sku":"110090181","name":"Q-Scout Robot Building Kit Line Follower","referenceSections":{
            "certification_info_tech":{"tables":[{"rows":[["Microcontroller","Qmind (Arduino Uno)"],["Motor","hobby motor (blue)"],
                                                        ["Types of parts","24"],["Total parts quantity","65"]]}],"source":"official store"}}}
        record={"sha256":product_tables.DIGESTS[guide]}
        self.assertFalse(product_tables.source_rows(guide,product,record))
        changes=product_tables.document_conflicts(guide,product,record,{})
        self.assertEqual(len(changes),4)
        self.assertTrue(changes[0]["source"].endswith("#page=3"))
        self.assertFalse(product_tables.document_conflicts(guide,product,{"sha256":"unreviewed revision"},{}))

    def test_region_specific_store_confirms_gateway_box_and_option_names(self):
        url=product_tables.GATEWAY_ADAPT
        items=[("Long Range Gateway",1),("Long Range Antenna",1),("4G Antenna",1),("Allen Hex Key",1),
               ("Mounts",4),("Power Adapter",1),("Power Extension Cable (5M)",1),("Ferrules / Aluminum piece","2 / 2"),("M5 Self-drilling Screws",8)]
        product={"sku":"102991375","name":"SenseCAP Outdoor Gateway - LoRaWAN AS923","parts":[[n,"x"+str(q)] for n,q in items],
                 "accessories":[{"name":n,"type":"商品页标明选配","source":"official store"} for n in ("Antenna Lightning Protector","Long Range Antenna Brackets","Long Range Fiberglass Omni Antenna")]}
        facts=product_tables.source_rows(url,product,{"sha256":product_tables.DIGESTS[url]})
        self.assertEqual(len(facts),13)
        self.assertTrue(all(r["source"].endswith("#page=76") for r in facts))
        merge_rows(product,facts,{})
        merge_rows(product,facts,{})
        self.assertEqual((len(product["parts"]),len(product["accessories"])),(9,3))
        self.assertTrue(all(a.get("documentedAsAccessorySource") for a in product["accessories"]))
        product["parts"][0][1]="x2"
        self.assertFalse(product_tables.source_rows(url,product,{"sha256":product_tables.DIGESTS[url]}))

    def test_older_pdf_partlist_marker_does_not_turn_component_bom_into_box(self):
        raw={"kind":"inbox","name":"Capacitor","quantity":"2","source":"https://files.seeedstudio.com/board.pdf#page=2"}
        record={"rows":[raw],"sections":[{"page":2,"heading":"Partlist","explicitBox":True}]}
        self.assertEqual(accepted(record,"sku","document_sku","123456789"),[])
        record["sections"][0]["heading"]="Package contents"
        self.assertEqual(accepted(record,"sku","document_sku","123456789")[0]["name"],"Capacitor")

    def test_inline_ocr_checks_identical_bytes_once_and_skips_protected_sources(self):
        from .document_ocr import inline_checker
        with patch.object(Path,"is_file",return_value=False),patch.object(Path,"open",mock_open()), \
             patch("backend.document_ocr.inspect",return_value={"status":"no_target_found","pages":2,"pagesWithText":2}) as read:
            check=inline_checker(Path("fixture"),Path("renderer"),60)
            record={"reason":"no_text_layer","pages":2,"sha256":"same"}
            check("https://files.seeedstudio.com/a.pdf",b"file",record)
            check("https://files.seeedstudio.com/b.pdf",b"file",record)
            check("https://files.seeedstudio.com/protected.pdf",b"other",{"reason":"protected_pdf","sha256":"other"})
            check("https://files.seeedstudio.com/board-schematic.pdf",b"third",{"reason":"no_text_layer","sha256":"third"})
            self.assertEqual(read.call_count,1)

    def test_digest_verified_text_pages_are_separate_from_early_url_only_counts(self):
        urls=["https://files.seeedstudio.com/"+i+".pdf" for i in "abc"]
        traces={"owner":{"sources":[{"url":u,"kind":"pdf","status":"empty"} for u in urls],"rows":[]}}
        records={u:{"kind":"pdf","status":"empty","pages":8} for u in urls}
        for u in urls[:2]:records[u]["sha256"]="same-edition"
        with patch("backend.document_merge.audit",return_value=(traces,{"pdf":Counter(empty=3)},{})), \
             patch("backend.document_merge.log_records",return_value=records),patch("backend.document_merge.atomic_write"):
            summary=write_bundle({"products":[]},Path("fixture"))
        self.assertEqual((summary["pdfTextPages"],summary["pdfTextPagesWithoutDigest"],summary["pdfTextFilesWithoutDigest"]),(8,8,1))
        self.assertEqual(summary["pdfPagesInCompletedTextPasses"],16)

    def test_publisher_bucket_requires_exact_public_object_and_respects_publisher_restriction(self):
        base="https://s3-us-west-2.amazonaws.com/files.seeedstudio.com/products/101990654/res/"
        target=base+"sensor.pdf"
        self.assertEqual(scanner.bucket_key(target),"products/101990654/res/sensor.pdf")
        for invalid in [target.replace("files.seeedstudio.com/","another-bucket/"),target+"?signature=example",base+"../other.pdf"]:
            self.assertFalse(scanner.publisher_source(invalid))
        checker=scanner.Rules()
        with patch.object(checker,"policy",side_effect=lambda h:("ok",[("disallow","/products/")] if h=="files.seeedstudio.com" else [],1)):
            self.assertEqual(checker.allowed(target),"excluded_robots")
        checker.unavailable_publisher_keys.add(scanner.bucket_key(target))
        self.assertEqual(checker.fetch(target,"pdf")[0]["reason"],"publisher_source_unavailable")

    def test_family_service_needs_declared_sku_correct_product_role_and_manufacturer_offer(self):
        source="https://github.com/Seeed-Studio/wiki-documents/blob/"+"a"*40+"/sites/en/docs/guide.md"
        raw="\n".join(["---","title: Getting started with reComputer Mini","slug: /recomputer_jetson_mini_getting_started",
            "sku: 102111001, 114993593","---","The reComputer Mini product family.",COMMITMENT,'<a href="'+SERVICE+'">Customize Now</a>'])
        products={"102111001":{"name":"reComputer Mini J4012 - Intelligent Edge AI Computer"},
                  "114993593":{"name":"reComputer Mini Extension Board for Jetson"},"114993553":{"name":"reComputer Mini J4012 with Extension"}}
        result=explicit_service(raw,source,products)
        self.assertEqual(result["skus"],["102111001"])
        self.assertEqual(result["modelSource"],source+"#L4")
        self.assertEqual(result["source"],source+"#L7")
        self.assertIsNone(explicit_service(raw.replace("Customize Now","Click"),source,products))
        self.assertIsNone(explicit_service(raw.replace("recomputer_jetson_mini_getting_started","an_application"),source,products))

    def test_wiki_kit_exclusions_and_distinct_size_rows_need_edition_and_sku(self):
        base="https://github.com/Seeed-Studio/wiki-documents/blob/c9321cc04d695f7b89ed273908558854fe00ab50/sites/en/docs/example/"
        for slug,sku,name in [("Bracket_for_Infrared_Proximity_Sensor","110060011","Bracket for Infrared Proximity Sensor"),
                              ("Capacitance_Meter_Kit","405010003","Capacitance Meter Kit")]:
            r={"markdownSource":base+slug+".md","purchaseSkus":[sku]}
            p={"sku":sku,"name":name};url="https://wiki.seeedstudio.com/"+slug+"/"
            facts=checked_wiki_rows(url,p,r,{})
            if sku=="110060011":
                self.assertEqual([(x["name"],x["quantity"]) for x in facts if "rivet" in x["name"]],
                                 [("Plastic rivet, 3 × 5.5 mm","2"),("Plastic rivet, 2 × 4.8 mm","10")])
            else:self.assertEqual([(x["name"],x.get("quantity")) for x in facts],
                                  [("Power supply",None),("Capacitance-meter kit components (not itemized)",""),("Schematic",""),("Manual","")])
            self.assertFalse(checked_wiki_rows(url,{**p,"sku":"000000000"},r,{}))
            self.assertFalse(checked_wiki_rows(url,p,{**r,"markdownSource":r["markdownSource"].replace("c9321cc","changed")},{}))

    def test_outdoor_gateway_mounts_options_and_region_are_distinct(self):
        url=product_tables.OUTDOOR;record={"sha256":product_tables.DIGESTS[url]}
        p={"sku":"102991154","name":"SenseCAP Outdoor Gateway - LoRaWAN EU868MHz","url":"https://www.seeedstudio.com/example.html"}
        facts=product_tables.source_rows(url,p,record)
        self.assertEqual({r["name"]:r["quantity"] for r in facts if r["kind"]=="inbox"}["Mounts"],"4")
        self.assertEqual(sum(r["kind"]=="inbox" for r in facts),9)
        self.assertEqual(sum(r["kind"]=="accessory" for r in facts),3)
        self.assertTrue(all(r["source"].endswith("#page=41") and r["modelSource"]==p["url"] for r in facts))
        self.assertEqual([r["name"] for r in facts if r["kind"]=="exclusion"],["LoRa fiberglass omnidirectional antenna"])
        self.assertFalse(product_tables.source_rows(url,{**p,"name":"SenseCAP Outdoor Gateway - LoRaWAN AU915"},record))

    def test_model_columns_and_disputed_vna_cable(self):
        url=product_tables.UARM;r={"sha256":product_tables.DIGESTS[url]}
        for sku,name,voltage in [("110991030","uArm Swift","6V DC"),("110991031","uArm Swift Pro","12V DC")]:
            self.assertEqual(product_tables.source_rows(url,{"sku":sku,"name":name},r)[0]["value"],voltage)
        vna=product_tables.JNCRADIO;record={"sha256":product_tables.DIGESTS[vna]}
        p={"sku":"113991034","name":"Chelegance JNCRadio VNA","parts":[["20cm SMA-JJ RG316 cable","x2"],["Stylus","1"]]}
        self.assertEqual([r["name"] for r in product_tables.source_rows(vna,p,record)],["Stylus"])
        self.assertEqual(product_tables.document_conflicts(vna,p,record,{})[0]["field"],"cableModel")

    def test_merchandising_offer_keeps_store_source_when_manual_independently_names_exact_sku(self):
        product={"sku":"a","accessories":[{"sku":"b","name":"B board","type":"商品页 Also Add 加购项","source":"https://www.seeedstudio.com/a.html"},
                                          {"sku":"c","name":"C store offer","type":"商品页 Also Add 加购项","source":"https://www.seeedstudio.com/a.html"}]}
        pdf="https://files.seeedstudio.com/manual.pdf";row={"kind":"accessory","sku":"b","name":"B expansion board",
            "scope":"family","family":"Board series","basis":"checked","source":pdf+"#page=10","documentUrl":pdf}
        merge_rows(product,[row],{});merge_rows(product,[row],{})
        self.assertEqual(len(product["accessories"]),2)
        first,other=product["accessories"]
        self.assertEqual((first["source"],first["documentedAsAccessorySource"]),("https://www.seeedstudio.com/a.html",pdf+"#page=10"))
        self.assertEqual(first["documentedAsAccessoryScope"],"Board series")
        self.assertNotIn("documentedAsAccessorySource",other)

    def test_super_adapter_matches_printed_orin_module_variant(self):
        url=product_tables.SUPER;record={"sha256":product_tables.DIGESTS[url],"pageSkus":{"7":["114110311","114110314"]}}
        for code,model,adapter,wrong in [("114110311","J3010","313080482","313080684"),("114110314","J4012","313080684","313080482")]:
            facts=product_tables.source_rows(url,{"sku":code,"name":"reComputer Super "+model+" - edge computer"},record)
            options={r.get("sku") for r in facts if r["kind"]=="accessory"}
            self.assertEqual(len(options),31)
            self.assertIn(adapter,options)
            self.assertNotIn(wrong,options)
            self.assertNotIn("112990226",options)

    def test_changed_unreadable_file_cannot_inherit_old_table(self):
        url="https://files.seeedstudio.com/v1.pdf"
        events=[{"url":url,"kind":"pdf","sha256":"old","status":"parsed","rows":[{"name":"A"}]},
                {"url":url,"kind":"pdf","sha256":"new","status":"unread","reason":"protected_pdf"}]
        with patch.object(Path,"is_file",lambda p:p.name=="document-checks.jsonl"),patch.object(Path,"read_text",lambda p,encoding:"\n".join(map(json.dumps,events))):
            result=log_records(Path("fixture"))[url]
        self.assertEqual(result["previousEdition"]["sha256"],"old")
        self.assertEqual(result["status"],"unread")
        self.assertNotIn("rows",result)

    def test_robotics_installed_disk_and_kit_are_separate_from_option_and_lens_disputes(self):
        url=product_tables.ROBOTICS
        record={"sha256":product_tables.DIGESTS[url],"pageSkus":{"7":["114110310","114110327"]}}
        host={"sku":"114110310","name":"reComputer Robotics J4012 - edge computer"}
        facts=product_tables.source_rows(url,host,record)
        self.assertEqual([f["kind"] for f in facts if f.get("sku")=="112990226"],["inbox"])
        self.assertEqual(next(f["source"] for f in facts if f.get("sku")=="E24121001"),url+"#page=66")
        self.assertFalse(any(f.get("sku")=="114110129" for f in facts))
        current={"114110129":{"name":"OV5647-67 FOV IR Camera","url":"https://www.seeedstudio.com/example.html"}}
        self.assertEqual(product_tables.document_conflicts(url,host,record,current)[0]["publishedSku"],"114110129")
        self.assertFalse(product_tables.source_rows(url,{"sku":"114110327","name":"reComputer Robotics J401 carrier board"},record))
        self.assertFalse(product_tables.source_rows(url,host,{**record,"sha256":"new edition"}))

    def test_weather_printed_skus_only_and_separately_ordered_mounts(self):
        url=product_tables.WEATHER;record={"sha256":product_tables.DIGESTS[url],"pageSkus":{"9":["101991044"]}}
        p={"sku":"101991044","name":"SenseCAP S200 Wind Speed and Direction Sensor"}
        rows=product_tables.source_rows(url,p,record)
        self.assertEqual(len([r for r in rows if r["kind"]=="inbox"]),3)
        self.assertEqual(len([r for r in rows if r["kind"]=="exclusion"]),3)
        self.assertFalse(product_tables.source_rows(url,{**p,"name":"SenseCAP S200-A"},record))
        self.assertFalse(product_tables.source_rows(url,{**p,"sku":"101991141"},record))

    def test_ocr_is_reused_only_for_matching_content_and_context_stays_local(self):
        def url(name):return "https://files.seeedstudio.com/"+name+".pdf"
        checks=[{"url":url(name),"kind":"pdf","status":"unread","reason":"no_text_layer","sha256":code} for name,code in (("a","ab"),("b","ab"),("c","cd"))]
        ocr={"url":url("a"),"sha256":"ab","status":"candidate_review","pages":2,"pagesWithText":2,"candidates":[{"page":1,"heading":"Accessories List"}]}
        files={"document-checks.jsonl":"\n".join(map(json.dumps,checks)),"document-ocr.jsonl":json.dumps(ocr)}
        with patch.object(Path,"is_file",lambda p:p.name in files),patch.object(Path,"read_text",lambda p,encoding:files[p.name]):
            r=log_records(Path("fixture"))
        self.assertEqual(r[url("b")]["ocrSameBytesAs"],url("a"))
        self.assertEqual(candidate_section_links(url("b"),r[url("b")])[0]["url"],url("b")+"#page=1")
        self.assertNotIn("ocrStatus",r[url("c")])

    def test_included_component_links_and_ambiguous_or_missing_targets(self):
        p={"sku":"910000000","parts":[["Cable","1"],["Board","1"],["Antenna","1"]]}
        ids={"910000001":{"name":"Cable"},"910000002":{"name":"Board"},"910000003":{"name":"Board"}}
        pairs=[("Cable","910000001"),("Board","910000002"),("Board","910000003"),("Antenna","910000004")]
        rows=[{"kind":"inbox","name":n,"sku":s,"source":"https://wiki.seeedstudio.com/test/#package-contents","scope":"sku"} for n,s in pairs]
        merge_rows(p,rows,ids)
        self.assertEqual(p["partProductSkus"],{"Cable":"910000001"})
        self.assertNotIn("accessories",p)

    def test_candidate_section_links_point_to_observed_physical_pages_only(self):
        self.assertTrue(scanner.PDF_HEADING.fullmatch("Chapter 9. Accessories List"))
        self.assertTrue(scanner.PDF_HEADING.fullmatch("Table 35. Accessories List"))
        self.assertTrue(scanner.PDF_HEADING.fullmatch("Accessories Information"))
        url="https://files.seeedstudio.com/guide.pdf"
        checked={"pages":5,"sections":[{"page":2,"kind":"inbox"},{"page":7,"kind":"inbox"}],
                 "ocrSections":[{"page":3,"heading":"Accessories List"}]}
        self.assertEqual([r["url"] for r in candidate_section_links(url,checked)],[url+"#page=2",url+"#page=3"])
        self.assertEqual(accepted(checked,"sku","reviewed","123456789"),[])

    def test_numbered_shipping_list_preserves_sku_and_does_not_treat_position_as_quantity(self):
        text="## Package Contents\n1. Board  SKU:101020232\n2. [USB cable](/cable)\n3. Connect the cable\n"
        parsed=parse_markdown(text,"https://wiki.seeedstudio.com/test/","https://github.com/Seeed-Studio/wiki-documents/blob/revision/test.md",[],"Test kit")
        self.assertEqual([(r["name"], r.get("sku"),r.get("quantity")) for r in parsed["rows"]],
                         [("Board","101020232",None),("USB cable",None,None)])
        self.assertEqual(scanner.kind("https://www.seeedstudio.com/wiki/SD_Card_Shield"),"wiki")
        self.assertEqual(scanner.kind("https://www.seeedstudio.com/wiki/images/SD_Card_Shield.jpg"),"reference")

    def test_numbered_pdf_pack_list_ends_before_installation(self):
        text="Board manual\fPackage Contents\n1. RTC board\n2) USB cable\nInstallation\n3. Download the software\n"
        response=type("Run",(),{"stdout":text.encode(),"returncode":0})()
        with patch.object(scanner,"PDF_TEXT_TOOL","mocked"),patch.object(scanner.subprocess,"run",return_value=response):
            parsed=scanner.parse_pdf(b"%PDF-test","https://files.seeedstudio.com/kit.pdf")
        self.assertEqual([(r["name"],r.get("quantity")) for r in parsed["rows"]],[("RTC board",None),("USB cable",None)])

    def test_robot_longest_rule_and_case_sensitive_path(self):
        r=scanner.Rules()
        r.hosts["www.seeedstudio.com"]=("published",[("disallow","/datasheet/"),("disallow","/*.pdf$"),("allow","/public/product.pdf$")],1)
        self.assertEqual(r.allowed("https://www.seeedstudio.com/datasheet/one"),"excluded_robots")
        self.assertEqual(r.allowed("https://www.seeedstudio.com/DATASHEET/one"),"")
        self.assertEqual(r.allowed("https://www.seeedstudio.com/public/product.pdf"),"")
        self.assertEqual(r.allowed("https://www.seeedstudio.com/other.pdf"),"excluded_robots")

    def test_wiki_table_uses_name_not_purchase_button_and_keeps_qty(self):
        source="https://wiki.seeedstudio.com/test/"
        body=b"<article><h1>Board</h1><h2 id='package-contents'>Package contents</h2><table><tr><th>SKU</th><th>Part Name</th><th>Qty</th><th>Link</th></tr><tr><td>123456789</td><td>Test cable</td><td>2</td><td>Get One Now</td></tr></table></article>"
        result=scanner.parse_wiki(body,source)
        self.assertEqual(result["rows"],[{"kind":"inbox","name":"Test cable","source":source+"#package-contents","quantity":"2","sku":"123456789"}])

    def test_report_page_and_qty_for_private_use_bullet(self):
        text="Cover of product handbook\fPackage contents\n\uf0b7   1 x RFEAH-25 H-loop near field antenna\n\uf0b7   1 x Semirigid SMA cable\nPage 2 of 9\f"
        response=type("Run",(),{"stdout":text.encode(),"returncode":0})()
        with patch.object(scanner,"PDF_TEXT_TOOL","mocked"),patch.object(scanner.subprocess,"run",return_value=response):
            parsed=scanner.parse_pdf(b"%PDF-mock","https://files.seeedstudio.com/a.pdf")
        self.assertEqual(len(parsed["rows"]),2)
        self.assertEqual(parsed["rows"][0]["name"],"RFEAH-25 H-loop near field antenna")
        self.assertEqual(parsed["rows"][1]["source"],"https://files.seeedstudio.com/a.pdf#page=2")

    def test_shared_reference_alone_never_inherits_kit_and_board_contents(self):
        prod={"name":"Unit Model-10, 4GB","sku":"100000007","url":"https://www.seeedstudio.com/Test-p-71.html"}
        group={"direct":{prod["sku"],"100000008"}}
        self.assertIsNone(identity(prod,"https://wiki.seeedstudio.com/kit",{"title":"Getting Started with Kit Series","purchaseSkus":[prod["sku"]]},group))
        facts=accepted({"rows":[{"kind":"inbox","name":"GPU","quantity":"1","source":"https://wiki.seeedstudio.com/kit/#part-list"}]},
                       "sku","verified",prod["sku"])
        self.assertFalse(facts)

    def test_expansion_categories_have_no_invented_sku_and_merge_twice(self):
        p={"sku":"102110773","name":"EdgeLogix","parts":[],"accessories":[]}
        facts=edgelogix_facts(p["sku"])
        merge_rows(p,facts,{}); before=copy.deepcopy(p);merge_rows(p,facts,{})
        self.assertEqual(before,p)
        self.assertEqual(p["modelSpecs"][0]["value"],"8GB")
        self.assertEqual([o["sku"] for o in p["accessories"]],["",""])
        self.assertTrue(all(o["source"].endswith("#page=17") for o in p["accessories"]))

    def test_explicit_box_section_keeps_named_part_with_unknown_quantity(self):
        body=b"<article><h1>USB board</h1><h2 id='package-contents'>Package contents</h2><ul><li>USB-C cable</li><li>Optional battery</li></ul><h2 id='part-list'>Part List</h2><ul><li>JST connector</li></ul></article>"
        record=scanner.parse_wiki(body,"https://wiki.seeedstudio.com/usb-board/")
        facts=accepted(record,"sku","verified","100000007")
        p={"sku":"100000007"}
        merge_rows(p,facts,{})
        self.assertEqual(p["parts"],[["USB-C cable",""]])
        self.assertEqual(p["partSources"]["USB-C cable"],"https://wiki.seeedstudio.com/usb-board/#package-contents")

    def test_kit_table_excludes_tutorial_shopping_list_despite_same_article(self):
        url="https://wiki.seeedstudio.com/Grove_Inventor_Kit_for_microbit/"
        record={"url":url,"rows":[{"kind":"inbox","name":"Grove cable","source":url+"#parts-list","quantity":"7"},
            {"kind":"inbox","name":"micro:bit","source":url+"#part-list","quantity":"1"}]}
        self.assertEqual([r["name"] for r in accepted(record,"sku","reviewed","110060762")],["Grove cable"])

    def test_original_quantity_retained_and_document_disagreement_remains_visible(self):
        p={"sku":"100000000","url":"https://www.seeedstudio.com/board.html","parts":[["Bracket","x2"]]}
        row={"kind":"inbox","name":"Bracket","quantity":"1","source":"https://files.seeedstudio.com/guide.pdf#page=6","scope":"sku"}
        merge_rows(p,[row],{});merge_rows(p,[row],{})
        self.assertEqual(p["parts"],[["Bracket","x2"]])
        self.assertEqual(len(p["partConflicts"]),1)
        self.assertEqual(p["partConflicts"][0]["documentQuantity"],"1")

    def test_legacy_sensor_gateway_and_mt20_stay_separate(self):
        r={"pages":50,"sha256":VISUAL_DIGESTS[SENSECAP_V13]}
        own=sensecap_common_box({"name":"SenseCAP Wireless CO2 Sensor- LoRaWAN AS923 MHz"},r)
        self.assertEqual([(row["name"],row["quantity"]) for row in own][-2:],[("M4 self-drilling screw","4"),("M3 self-drilling screw","2")])
        self.assertTrue(all(row["scope"]=="family" and row["source"].endswith("#page=11") for row in own))
        self.assertFalse(sensecap_common_box({"name":"SenseCAP Wireless Soil Temperature, VWC & EC Sensor - LoRaWAN EU868 -MT20"},r))
        self.assertFalse(sensecap_common_box({"name":"SenseCAP Outdoor Gateway - LoRaWAN AU915"},r))

    def test_s2100_separate_optional_kit_is_never_in_the_sensor_box(self):
        logger={"name":"SenseCAP S2100 - LoRaWAN Data Logger","sku":"114992872"}
        probe={"name":"RS485 750cm Ultrasonic Level Sensor","sku":"101991041"}
        kit={"name":"Waterproof Junction Box Kit, Connecting Box for S2100 Data Logger","url":"https://www.seeedstudio.com/box.html"}
        reviewed={"pages":69,"sha256":VISUAL_DIGESTS[S2100_PDF]}
        rows=exact_model_rows(S2100_PDF,logger,reviewed,{"114992988":kit})
        self.assertEqual(len([r for r in rows if r["kind"]=="inbox"]),4)
        self.assertEqual([r["sku"] for r in rows if r["kind"]=="accessory"],["114992988"])
        self.assertFalse(exact_model_rows(S2100_PDF,probe,reviewed,{}))
        self.assertFalse(exact_model_rows(S2100_PDF,logger,{**reviewed,"sha256":"new edition"},{}))

    def test_reserver_complete_box_and_optional_radio_variants(self):
        sku="114992628"
        p={"sku":"110061403","name":"reServer J2032 - NVIDIA Jetson","parts":[["Carrier Board","1"],["Bottom Fan","1"]],
           "accessories":[{"type":"商品页 Also Add 加购项","sku":sku}],"url":"https://www.seeedstudio.com/item.html"}
        radio={"sku":sku,"name":"Wio-WM1302 Long Range Gateway Module(USB) - EU868","url":"https://www.seeedstudio.com/radio.html"}
        rows=exact_model_rows(J2032_PDF,p,{"pages":17,"sha256":VISUAL_DIGESTS[J2032_PDF]},{sku:radio})
        merge_rows(p,[{**f,"documentUrl":J2032_PDF} for f in rows],{sku:radio})
        self.assertEqual(len(p["parts"]),4)
        self.assertEqual(p["alternatePackingLists"][0]["kind"],"assembly_components")
        self.assertEqual(p["alternatePackingLists"][0]["parts"],[["Carrier Board","1"],["Bottom Fan","1"]])
        self.assertEqual(len(p["accessories"]),3)
        self.assertEqual(p["accessories"][0]["documentedAsAccessorySource"],J2032_PDF+"#page=14")
        self.assertTrue(all(option.get("notIncludedSource")==J2032_PDF+"#page=14" for option in p["accessories"]))
        self.assertEqual([a.get("sku") for a in p["accessories"]],[sku,"",""])

    def test_single_declared_sku_does_not_validate_application_or_multi_sku_contents(self):
        p={"sku":"123456789","name":"XIAO board"};link={"direct":set()}
        single={"title":"XIAO board","declaredSkus":[p["sku"]],"sourceScopes":["product"]}
        self.assertEqual(identity(p,"https://wiki.seeedstudio.com/board",single,link),("sku","declared_product_sku_and_title"))
        for meta in [{"sourceScopes":["application"]},{"sourceScopes":["multi_sku"]},{"sourceScopes":["link_only"]},{"declaresMultiple":True}]:
            self.assertIsNone(identity(p,"https://wiki.seeedstudio.com/board",{**single,**meta},link))

    def test_nonnumeric_sku_requires_a_real_catalogue_id_and_labelled_field(self):
        scanner.set_catalog_skus(["E24081601","B17","123456789"])
        try:
            accepted_rows=[];rejected=[];external=[]
            scanner.add_rows(accepted_rows,["Option board","E24081601"],"accessory","https://example.test",["Product Name","SKU"])
            scanner.add_rows(external,["Option board","E24081699"],"accessory","https://example.test",["Product Name","SKU"])
            scanner.add_rows(rejected,["E24081601 module"],"accessory","https://example.test")
            self.assertEqual([r["sku"] for r in accepted_rows],["E24081601"])
            self.assertEqual(rejected,[])
            self.assertEqual(external[0]["publishedSku"],"E24081699")
            self.assertNotIn("sku",external[0])
            self.assertEqual(scanner.labelled_skus("B17 IC, SKU: E24081601"),["E24081601"])
        finally:scanner.set_catalog_skus([])

    def test_unknown_publisher_codes_survive_pdf_and_merge_without_local_link(self):
        content="Product manual\nAccessories List\nProduct Name     SKU\nTest antenna     VENDOR123\nTest antenna     VENDOR124\f"
        run=type("Run",(),{"stdout":content.encode(),"returncode":0})()
        with patch.object(scanner,"PDF_TEXT_TOOL","test"),patch.object(scanner.subprocess,"run",return_value=run):
            result=scanner.parse_pdf(b"%PDF-mock","https://files.seeedstudio.com/board.pdf")
        facts=accepted(result,"sku","verified_table","123456789")
        product={"sku":"123456789"}
        merge_rows(product,facts,{})
        self.assertEqual([a["publishedSku"] for a in product["accessories"]],["VENDOR123","VENDOR124"])
        self.assertTrue(all(a["sku"]=="" for a in product["accessories"]))

    def test_counted_chinese_box_names_from_overseas_documents_are_distinct(self):
        body="<article><h1>Test board</h1><h2 id='装箱清单'>装箱清单</h2><table><tr><th>产品名称</th><th>数量</th></tr><tr><td>支架</td><td>2件</td></tr><tr><td>天线</td><td></td></tr></table></article>".encode()
        records=scanner.parse_wiki(body,"https://wiki.seeedstudio.com/board/")
        p={"sku":"123456789"};merge_rows(p,accepted(records,"sku","model","123456789"),{})
        self.assertEqual(p["parts"],[["支架","2"],["天线",""]])

    def test_checkout_rows_link_to_exact_published_line(self):
        text="---\ntitle: Board\n---\n# Board\n## Package contents\n| Part Name | Qty |\n| --- | --- |\n| USB cable | 2 |"
        r=parse_markdown(text,"https://wiki.seeedstudio.com/test/","https://github.com/Seeed-Studio/wiki-documents/blob/sha/file.md",["123456789"],"Board")
        self.assertEqual(r["rows"][0]["source"].split("#")[1],"L8")
        self.assertEqual(r["rows"][0]["quantity"],"2")

    def test_visually_verified_table_keeps_publisher_part_number_and_exact_quantity(self):
        p={"sku":"110990061","name":"2WD Arduino compatible Mobile platform"}
        rows=reviewed_rows(TWO_WHEEL_URL,p,{"pages":12,"sha256":VISUAL_DIGESTS[TWO_WHEEL_URL]})
        self.assertEqual(len(rows),24)
        self.assertEqual(next(r for r in rows if r.get("partNumber")=="M0507")["quantity"],"19")
        self.assertTrue(all("sku" not in r and r["source"].endswith("#page=12") for r in rows))
        self.assertEqual(reviewed_rows(ATV_URL,p,{"pages":1,"sha256":VISUAL_DIGESTS[ATV_URL]}),[])
        self.assertEqual(reviewed_rows(TWO_WHEEL_URL,p,{"pages":12,"sha256":"new edition"}),[])

    def test_complete_manual_keeps_the_alternative_store_assembly_list_separate(self):
        p={"sku":"110990061","name":"2WD Arduino compatible Mobile platform","url":"https://www.seeedstudio.com/2wd.html",
           "parts":[["Aluminium chassis","1"],["wheels","2"],["Motors","2"],["Omni-directional Wheel","1"]]}
        original=copy.deepcopy(p["parts"])
        rows=reviewed_rows(TWO_WHEEL_URL,p,{"pages":12,"sha256":VISUAL_DIGESTS[TWO_WHEEL_URL]})
        merge_rows(p,rows,{});merge_rows(p,rows,{})
        self.assertEqual(len(p["parts"]),24)
        self.assertEqual(p["alternatePackingLists"],[{"source":p["url"],"kind":"storefront","parts":original}])
        self.assertEqual(p["partSource"],TWO_WHEEL_URL+"#page=12")

    def test_independent_list_names_and_materials_do_not_double_count(self):
        p={"sku":"123456789","parts":[["Rivet · R2056 · White nylon","20"],["Rivet · R2064 · Black nylon","20"]]}
        rows=[{"kind":"inbox","name":"Rivet ("+part+")","source":"https://wiki.seeedstudio.com/Kit/#list","quantity":"20",
               "scope":"sku","documentUrl":"https://wiki.seeedstudio.com/Kit/"} for part in ("R2056","R2064")]
        merge_rows(p,rows,{});merge_rows(p,rows,{})
        self.assertEqual(len(p["parts"]),2)
        self.assertEqual(p["alternatePackingLists"][0]["parts"],[["Rivet (R2056)","20"],["Rivet (R2064)","20"]])
        self.assertEqual(len(p["alternatePackingLists"]),1)

    def test_official_github_file_is_limited_to_explicit_publisher_and_pdf(self):
        url="https://github.com/SeeedDocument/Board/raw/master/doc/Manual.pdf"
        self.assertEqual(scanner.github_file(url)[0],"https://api.github.com/repos/SeeedDocument/Board/contents/doc/Manual.pdf?ref=master")
        self.assertIsNone(scanner.github_file(url.replace("SeeedDocument","unknown-other-org")))
        self.assertIsNone(scanner.github_file(url.replace(".pdf",".zip")))


if __name__=="__main__":unittest.main()
