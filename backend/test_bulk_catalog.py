import json
from pathlib import Path
import tempfile
from contextlib import closing
import unittest
from .bulk_catalog import body_sections,content_state
from .catalog_release import inventory_digest
from .storage import CATALOG_PREFIX,Store,Problem,packed,write
from .store_policy import Policy
from .storefront import OfficialStore,extract_detail,product_link_index,product_link_key
from .extract import tree,section_parts,links,wiki_references,facts,valid_part_name,body_options,text_link,merge_part_purposes
from .updates import Updates,digest,refresh_facts


class PublicSources(unittest.TestCase):
    def test_merged_robots_rules_and_redirects(self):
        host="https://www.seeedstudio.com"
        text="User-agent: *\nDisallow: /api/\nDisallow: *-t-*.html\nAllow: *-t-*-p-*.html$\nUser-agent:*\nDisallow: /catalog/\nUser-agent: Other\nDisallow: /\n"
        p=Policy(text)
        self.assertTrue(p.allows(host+"/graphql"))
        for route in ["/api/X","/catalog/product/view/id/3","/old-t-12.html"]:self.assertFalse(p.allows(host+route))
        self.assertTrue(p.allows(host+"/old-t-7-p-8.html"))
        class InMemory(OfficialStore):
            hits=[]
            def raw_get(self,url,*args):
                self.hits.append(url)
                return text.encode() if url.endswith("robots.txt") else b"legitimate"
        s=InMemory()
        with self.assertRaisesRegex(Problem,"ROBOTS_EXCLUDED"):s.get(host+"/catalog/product/view/id/3")
        self.assertEqual(s.hits,[host+"/robots.txt"])
        self.assertFalse(s.redirect_allowed(host+"/catalog/bar"))

    def test_body_and_ten_columns_are_independent(self):
        body="<h2>Features</h2><ul><li>2GB memory</li></ul><h2>Resources</h2><p><a href='sheet.pdf'>Datasheet</a></p>"
        self.assertEqual(set(body_sections(body)),{"product_feature_description","documents"})
        self.assertEqual(content_state("<p><br/></p>"),"empty")
        self.assertEqual(content_state("<style>.table{width:100%}</style><p> &nbsp; </p>"),"empty")
        self.assertEqual(content_state("<p><img src='diagram.jpg'/></p>"),"present")
        self.assertEqual(content_state({}),"empty")
        previous={"url":"https://www.seeedstudio.com/A.html","accessories":[{"sku":"B","type":"商品页 Also Add 加购项"}]}
        current={"name":"A","url":previous["url"],"notes":[],"parts":[],"docs":[],"wikiLinks":[],"details":True}
        self.assertEqual(refresh_facts(previous,current,None,{})["accessories"],previous["accessories"])
        self.assertEqual(refresh_facts(previous,current,[],{})["accessories"],[])

    def test_robots_error_document_blocks_page_requests(self):
        site="https://www.seeedstudio.com/"
        class Fake(OfficialStore):
            def __init__(self,reply):super().__init__();self.reply=reply;self.read=[]
            def raw_get(self,url,*args):
                self.read.append(url)
                if url.endswith("robots.txt"):
                    if isinstance(self.reply,Problem):raise self.reply
                    return self.reply
                return b"public product"
        for body in (b"<!DOCTYPE html><html><body>Try again</body></html>",b"Service unavailable",b'{"error":"temporarily unavailable"}',b"\xff\x00"):
            remote=Fake(body)
            with self.assertRaisesRegex(Problem,"ROBOTS_UNVERIFIED"):remote.get(site+"p.html")
            self.assertEqual(remote.read,[site+"robots.txt"])
        for body in (b"",b"# no directives",Problem("STORE_HTTP_404"),b"\xef\xbb\xbfUser-agent: *\nAllow: /\n"):
            self.assertEqual(Fake(body).get(site+"p.html"),b"public product")

    def test_fastener_pack_name_model_description_and_rowspan(self):
        body="""<h2>Part List</h2><table><tr><th>Part Name</th><th>Specification</th>
                <th>Description</th><th>Image</th><th>Quantity</th></tr>
                <tr><td rowspan="2">Rivet</td><td>R2056</td><td>White nylon</td><td></td><td>20</td></tr>
                <tr><td>R2064</td><td>Black nylon</td><td></td><td>20</td></tr>
                <tr><td>/</td><td>-</td><td>N/A</td><td></td><td>1</td></tr></table>"""
        rows=section_parts(tree(body))
        self.assertEqual(rows,[["Rivet · R2056 · White nylon","20"],["Rivet · R2064 · Black nylon","20"]])
        src="https://www.seeedstudio.com/kit.html"
        prior={"url":src,"parts":[["/","1"]],"partSource":src,"storePartStatus":"present","partStatus":"present"}
        fresh={"url":src,"name":"Kit","parts":rows,"partSources":{n:src for n,_ in rows},"details":False}
        result=refresh_facts(prior,fresh,None,{})
        self.assertEqual(result["parts"],rows)
        self.assertEqual(result["storePartStatus"],"unparsed")
        self.assertEqual(result["unclassifiedRows"],[["/","1"]])

    def test_reference_columns_replace_only_verified_members(self):
        url="https://www.seeedstudio.com/example.html"
        prev={"url":url,"referenceSections":{"faq_list":{"text":["old question"]},
              "hardware_overview":{"text":["unread field survives"]}}}
        cur={"name":"Example","url":url,"notes":[],"docs":[],"wikiLinks":[],"parts":[]}
        extract_detail(cur,{"faq_list":"","certification_info_tech":"<table><tr><td>Weight</td><td>28 g</td></tr></table>"})
        merged=refresh_facts(prev,cur,None,{})
        self.assertEqual(set(merged["referenceSections"]),{"hardware_overview","certification_info_tech"})
        self.assertIn("28 g",str(merged["referenceSections"]["certification_info_tech"]))
        self.assertNotIn("_readReferenceSections",merged)

    def test_specific_in_box_disclaimer_is_visible_without_claiming_a_part(self):
        url="https://www.seeedstudio.com/example.html";phrase="The Tape & Reel board doesn‘t come with 7-pin headers."
        previous={"url":url,"storePartStatus":"unparsed","unclassifiedRows":[[phrase]],"unclassifiedSource":url}
        current={"name":"XIAO","url":url,"notes":[],"parts":[],"docs":[],"wikiLinks":[],"details":False}
        merged=refresh_facts(previous,current,None,{})
        self.assertEqual(merged["parts"],[])
        self.assertEqual(merged["notes"],[{"kind":"另购说明","text":phrase,"source":url}])

    def test_old_http_image_only_wiki_and_odm_service_scope(self):
        url="https://www.seeedstudio.com/selected.html"
        fragment=tree('<a href="http://Wiki.seeedstudio.com/Grove-Rotary_Angle_Sensor/#Read"><img alt="Rotary sensor guide" src="a"></a>'
                      '<a href="http://wiki.seeedstudio.com/Stem_-_Base_Shield/"><img src="b"></a>'
                      '<p>Seeed Agile ODM Service empowers customers with our customizable services including image flashing and logo change.</p><p>Customize your code.</p>')
        got=wiki_references(links(fragment,url))
        self.assertEqual(got,[{"title":"Rotary sensor guide","url":"https://wiki.seeedstudio.com/Grove-Rotary_Angle_Sensor/#Read"},
                              {"title":"Stem - Base Shield","url":"https://wiki.seeedstudio.com/Stem_-_Base_Shield/"}])
        notes=facts(fragment,url)
        self.assertEqual(len(notes),1);self.assertEqual(notes[0]["scope"],"service")
        self.assertTrue(notes[0]["source"].startswith(url+"#:~:text="))
        from .storage import customization_info
        self.assertIsNone(customization_info({"name":"Jetson module","url":url,"notes":notes}))

    def test_ordinals_do_not_survive_their_named_rows_or_add_optional_items(self):
        url="https://www.seeedstudio.com/example.html"
        doc=tree('<h2>Part List</h2><div><table><tr><td>1</td><td>Gateway</td><td>x1</td></tr>'
                 '<tr><td>2</td><td>Ferrules / plates</td><td>x2 / 2</td></tr></table>'
                 '<table><tr><td colspan="3">*Optional Antenna</td></tr><tr><td>1</td><td>Omni antenna</td><td>x1</td></tr></table></div>')
        named=section_parts(doc)
        self.assertEqual(named,[["Gateway","x1"],["Ferrules / plates","x2 / 2"]])
        self.assertTrue(valid_part_name("114992548"));self.assertTrue(valid_part_name("18650"))
        old={"url":url,"parts":[["1","x1"]],"partStatus":"present","storePartStatus":"empty"}
        cur={"url":url,"name":"Gateway","parts":named,"partSources":{n:url for n,_ in named},"details":False}
        joined=refresh_facts(old,cur,None,{})
        self.assertEqual(joined["storePartStatus"],"empty");self.assertEqual(joined["parts"],named)
        options=body_options(doc,url)
        self.assertEqual([o["name"] for o in options],["Omni antenna"])
        self.assertNotIn("sku",options[0]);self.assertEqual(options[0]["type"],"商品页标明选配")

    def test_dimensions_are_not_quantities_and_stale_body_parse_is_replaced(self):
        url="https://www.seeedstudio.com/example.html"
        contents=section_parts(tree('<h2>Part List</h2><ul><li>4 x Distance holder M3*25</li><li>Screw M2.5*20</li></ul>'))
        self.assertEqual(contents,[["Distance holder M3*25","4"],["Screw M2.5*20",""]])
        wrong="4 x Distance holder M3"
        old={"url":url,"parts":[[wrong,"25"],["Manual accessory","1"]],"storePartStatus":"empty","partStatus":"present",
             "partSources":{wrong:text_link(url,wrong),"Manual accessory":"https://files.seeedstudio.com/manual.pdf#page=5"}}
        current={"name":"Kit","url":url,"details":False,"parts":contents,"partSources":{n:text_link(url,n) for n,_ in contents},"bodyStatus":"present"}
        final=refresh_facts(old,current,None,{})
        self.assertEqual(final["parts"],[["Manual accessory","1"],*contents])

    def test_use_descriptions_do_not_increase_the_in_box_count(self):
        url="https://www.seeedstudio.com/example.html"
        phrase="Grove - RTC to record the current time for your smart device"
        long=phrase.replace("RTC","Hub")
        record={"url":url,"parts":[["Grove - RTC","1"],[phrase,"1x"],["Grove - Hub","1"],[long,"2"],["USB to TTL","1"]],
                "partSources":{phrase:text_link(url,phrase)}}
        merge_part_purposes(record)
        self.assertEqual(len(record["parts"]),4)
        self.assertEqual(record["partDescriptions"]["Grove - RTC"],{"text":phrase,"source":text_link(url,phrase)})
        self.assertIn([long,"2"],record["parts"])

    def test_verified_industrial_packing_aliases_and_disagreeing_quantities(self):
        from .sku_packing import verified_aliases,SERVER_GUIDE,COMPUTER_GUIDE
        from .extract import install_column
        url="https://www.seeedstudio.com/industrial.html"
        p={"sku":"114110248","name":"reServer Industrial J4011","url":url,"parts":[["reServer Industrial J4011 (System Installed)","x 1"],
           ["reServer Industrial","1"],["Bracket Bolt","x 10"],["Bracket screw","x10"]]}
        verified_aliases(p)
        self.assertEqual(len(p["parts"]),2);self.assertEqual(p["partDescriptions"]["Bracket Bolt"]["crosscheck"],SERVER_GUIDE)
        c={"sku":"110110189","name":"reComputer Industrial J2012","url":url,"parts":[["Bracket screw","x4"]],"partSources":{"Bracket screw":text_link(url,"Bracket screw")}}
        install_column(c,"<table><tr><th>Item</th><th>Qty</th></tr><tr><td>Bracket screw</td><td>x1</td></tr></table>")
        verified_aliases(c)
        self.assertEqual(c["parts"],[["Bracket screw","x1"]]);self.assertEqual([r["scope"] for r in c["partQuantityConflicts"]["Bracket screw"]],["store_part_list","description","family"])
        self.assertEqual(c["partQuantityConflicts"]["Bracket screw"][-1]["source"],COMPUTER_GUIDE)

    def test_family_module_options_become_one_confirmed_super_configuration(self):
        from .sku_packing import verified_aliases,SUPER_GUIDE
        raw="Jetson Orin™ NX 16GB/NX 8GB /Nano 8GB/Nano 4GB module"
        p={"sku":"114110314","name":"reComputer Super J4012 with Jetson Orin NX 16GB","url":"https://www.seeedstudio.com/example.html","parts":[[raw,"x 1"],["SSD","1"]]}
        verified_aliases(p)
        precise="Jetson Orin™ NX 16GB module"
        self.assertEqual(p["parts"],[[precise,"x 1"],["SSD","1"]]);self.assertEqual(p["partSources"][precise],SUPER_GUIDE+"#page=7")
        self.assertEqual(p["partDescriptions"][precise]["text"],raw)
        wrong={"sku":"114110314","name":"reComputer Super J3010 with Nano 4GB","parts":[[raw,"1"]]}
        verified_aliases(wrong);self.assertEqual(wrong["parts"],[[raw,"1"]])

    def test_old_packing_tables_follow_styles_and_keep_actual_names(self):
        body="""<h2>Part List</h2><style>table {width:60%}</style><table>
        <tr><td>1</td><td>Sensor</td><td>1x</td></tr><tr><td>2</td><td>Bracket</td><td>1x</td></tr>
        <tr><td>3</td><td>M4 Self-drilling Screw</td><td>4x</td></tr></table>"""
        self.assertEqual(section_parts(tree(body)),[["Sensor","1x"],["Bracket","1x"],["M4 Self-drilling Screw","4x"]])
        mixed="<h2>Part List</h2><table><tr><td colspan='3'>2.4G Version</td></tr><tr><td>1 × Chassis</td><td>2 × Wheels</td></tr></table>"
        self.assertEqual(section_parts(tree(mixed)),[])
        self.assertEqual(section_parts(tree(mixed),"mBot v1.1 (2.4G Version)"),[["Chassis","1"],["Wheels","2"]])

    def test_packaging_in_a_comparison_needs_the_exact_model_column(self):
        page="""<table><tr><th>Feature</th><th>SARK-110</th><th>SARK-110-ULM</th></tr>
        <tr><td><strong>Package contents</strong></td><td><ul><li>Extra adapter x1</li></ul></td>
        <td><ul><li>SARK-110-ULM x 1 with built-in battery</li></ul></td></tr></table>"""
        self.assertEqual(section_parts(tree(page)),[])
        self.assertEqual(section_parts(tree(page),"SARK-110-ULM Antenna Analyzer"),[["SARK-110-ULM x 1 with built-in battery","1"]])

    def test_one_shop_url_cannot_leak_the_other_skus_details(self):
        page=b"""<div class="product attribute sku sku-section"><div itemprop="sku">110990471</div></div>
        <div class="related-product"><div itemprop="sku">110060306</div></div>
        <form id="product_addtocart_form"><input name="product" value="651"></form>
        <input id="PRODUCT_DETAIL_test" value='{"documents":"Manual"}'>"""
        record=OfficialStore.detail_payload(page,"110990471")
        OfficialStore.verify_entity_id(record,651)
        with self.assertRaisesRegex(Problem,"DETAIL_SKU_NOT_VERIFIED"):OfficialStore.verify_entity_id(record,364)
        with self.assertRaisesRegex(Problem,"DETAIL_SKU_NOT_VERIFIED"):OfficialStore.detail_payload(page,"110060306")

    def test_addon_links_resolve_percent_encoding_but_not_shared_or_variant_urls(self):
        domain="https://www.seeedstudio.com/"
        idx=product_link_index([("X",domain+"Cortex-M0%2B.html"),("A",domain+"kit.html"),("B",domain+"kit.html")])
        self.assertEqual(idx[product_link_key("/Cortex-M0+.html",domain)],"X")
        self.assertIsNone(idx[product_link_key(domain+"kit.html")])
        self.assertFalse(product_link_key(domain+"kit.html?selectedSku=B"))


class CompatiblePreview(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.path=self.root/"data/catalog.js"
        self.base={"products":[{"sku":"A","name":"Alpha"}],"categories":[],"stats":{}}
        self.save(self.base)
        self.old=digest(self.path)
        self.store=Store(self.root/"user",self.root)
        self.updates=Updates(self.store)
        with closing(self.updates.connect()) as db,db:self.updates.put(db,"baseDigest",self.old)

    def save(self,data):
        write(self.path,CATALOG_PREFIX.encode()+packed(data)+b";\n")

    def release(self,changed=False):
        data={**self.base,"products":[*self.base["products"],{"sku":"B","name":"Secondary","catalogStatus":"live_secondary"}]}
        data["audit"]={"previewCompatibility":{"sourceDigest":self.old,"fieldsDigest":inventory_digest(data),"addedSkus":["B"]}}
        if changed:data["products"][0]["name"]="Changed after release"
        self.save(data)

    def test_rebase_before_first_detail(self):
        self.release()
        with closing(self.updates.connect()) as db:
            self.updates.ensure_base(db)
            self.assertEqual(self.updates.get(db,"baseDigest"),digest(self.path))
            self.assertIn("b",self.store.by_sku)

    def test_conflicting_or_partially_completed_preview_is_untouched(self):
        self.release()
        with closing(self.updates.connect()) as db:
            for sku,done in (("b",0),("a",1)):
                with db:
                    db.execute("DELETE FROM pending")
                    db.execute("INSERT INTO pending VALUES (?,?,?)",(sku,"{}",done))
                with self.assertRaisesRegex(Problem,"LOCAL_CATALOG_CHANGED"):self.updates.ensure_base(db)
                self.assertEqual(self.updates.get(db,"baseDigest"),self.old)
            with db:db.execute("DELETE FROM pending")
            self.release(changed=True)
            with self.assertRaisesRegex(Problem,"LOCAL_CATALOG_CHANGED"):self.updates.ensure_base(db)

    def test_route_only_skus_refresh_selectively_without_false_missing(self):
        class Routes:
            touched=[]
            def route_product(self,url,sku):
                self.touched.append(sku)
                return {"id":22,"sku":sku,"name":"Route product","url_key":sku,"url_suffix":".html"}
        for sku in ("B","C"):
            self.store.by_sku[sku.lower()]={"sku":sku,"name":sku,"url":"https://www.seeedstudio.com/"+sku+".html",
                                          "catalogStatus":"live_secondary","groups":[]}
        self.updates.remote=Routes()
        with closing(self.updates.connect()) as db,db:
            self.updates.make_diff(db)
            self.assertEqual([s for s, in db.execute("SELECT sku FROM changes")],["A"])
            self.updates.put(db,"scope",{"skus":["B"],"categories":[]})
            self.updates.secondary_stage(db)
            self.assertEqual(self.updates.remote.touched,["B"])
            pending=json.loads(db.execute("SELECT p FROM pending").fetchone()[0])
            self.assertEqual(pending["catalogStatus"],"live_secondary")


if __name__=="__main__":unittest.main()
