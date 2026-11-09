"""Attachment facts require a reviewed workbook and exact kit identity."""
from io import BytesIO
import unittest
from zipfile import ZipFile

from . import document_sheet as sheets
from .document_enrichment import github_file, kind
from .document_merge import merge_rows
from . import document_compatibility as compatibility
from .document_scope import reconcile


class DocumentSheetTests(unittest.TestCase):
    def test_distinct_coverage_outcomes_preserve_unknown_historical_rate_receipts(self):
        origin="https://files.seeedstudio.com/"
        urls=[origin+str(n)+".pdf" for n in range(6)]
        checks={urls[0]:{"kind":"pdf","status":"empty"},urls[1]:{"kind":"pdf","status":"failed","reason":"http_404"},
                urls[2]:{"kind":"pdf","status":"unread","reason":"not_yet_checked"},urls[3]:{"kind":"pdf","status":"unread","reason":"github_rate_limit"},
                urls[4]:{"kind":"pdf","status":"unread","reason":"excluded_robots"},urls[5]:{"kind":"reference","status":"unread"}}
        summary=reconcile(checks,{urls[0]:{"markdownSource":"pinned"}},
                          {urls[0]:{"body","request"},urls[1]:{"request"},urls[3]:{"uncertain"}})
        self.assertEqual((summary["linked"],summary["eligible"],summary["excluded"]),(6,4,2))
        self.assertEqual([summary[k] for k in ("completed","attemptedIncomplete","notAttempted","attemptUncertain")],[1,1,1,1])
        self.assertEqual((summary["onlineRequested"],summary["originalReadUnion"],summary["onlineAndOfflineRead"]),(2,1,1))

    def test_workbook_is_read_only_and_quantity_is_optional(self):
        data=BytesIO()
        with ZipFile(data,"w") as z:
            z.writestr("xl/workbook.xml",'<workbook xmlns="'+sheets.NS[1:-1]+'" xmlns:r="'+sheets.RID[1:].split("}")[0]+'"><sheets><sheet name="Sheet1" r:id="rId1"/></sheets></workbook>')
            z.writestr("xl/_rels/workbook.xml.rels",'<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr("xl/worksheets/sheet1.xml",'<worksheet xmlns="'+sheets.NS[1:-1]+'"><sheetData>'
                       '<row r="1"><c r="A1" t="inlineStr"><is><t>SKU</t></is></c><c r="C1" t="inlineStr"><is><t>Product Name</t></is></c></row>'
                       '<row r="2"><c r="A2"><v>101020025</v></c><c r="C2" t="inlineStr"><is><t>Grove - Tilt Switch</t></is></c></row>'
                       '<row r="3"><c r="A3"><f>1+1</f><v>101020015</v></c><c r="C3" t="inlineStr"><is><t>A formula row</t></is></c></row>'
                       '</sheetData></worksheet>')
        result=sheets.parse(data.getvalue(),sheets.GROVE_GAMMA)
        self.assertEqual(result["status"],"unread")
        self.assertEqual(result["sheetRows"],[{"publishedSku":"101020025","name":"Grove - Tilt Switch","quantity":"","sheet":"Sheet1","row":2,"cellRange":"A2:C2"}])
        self.assertEqual(sheets.verified_rows(sheets.GROVE_GAMMA,{"sku":"110020230"},result,{}),[])
        self.assertEqual(sheets.parse(b"not a workbook",sheets.GROVE_GAMMA)["status"],"failed")

    def test_provenance_and_published_codes_survive_missing_store_matches(self):
        product={"sku":"110020230","name":"Grove Creator Kit - γ / 40 Grove functional modules in one box"}
        rows=[{"publishedSku":str(100000000+n),"name":f"Module {n}","sheet":"Sheet1","row":n,"cellRange":f"A{n}:C{n}","quantity":""} for n in range(2,42)]
        record={"sha256":sheets.GAMMA_DIGEST,"sheetRows":rows}
        by_sku={"100000002":{"sku":"100000002","name":"Module 2"}}
        verified=sheets.verified_rows(sheets.GROVE_GAMMA,product,record,by_sku)
        merge_rows(product,verified,by_sku)
        merge_rows(product,verified,by_sku)
        self.assertEqual(len(product["parts"]),40)
        self.assertTrue(all(r[1]=="" for r in product["parts"]))
        self.assertEqual(product["partProductSkus"],{"Module 2":"100000002"})
        self.assertEqual(product["partPublishedSkus"]["Module 41"],"100000041")
        self.assertEqual(product["partSourceLocations"]["Module 41"]["cellRange"],"A41:C41")
        for changes in ({"sku":"110020229"},{"name":"Grove Creator Kit - β / 40 Grove functional modules in one box"}):
            self.assertEqual(sheets.verified_rows(sheets.GROVE_GAMMA,{**product,**changes},record,by_sku),[])
        self.assertEqual(sheets.verified_rows(sheets.GROVE_GAMMA,product,{**record,"sha256":"changed"},by_sku),[])

    def test_github_compatibility_workbooks_use_same_public_api_and_unrelated_sheets_stay_links(self):
        book="https://github.com/SeeedDocument/Beaglebone_Blue/raw/master/res/Beaglebone%20Blue%20Grove%20Compatibility%20List.xlsx"
        self.assertEqual(kind(book),"spreadsheet")
        self.assertTrue(github_file(book)[0].startswith("https://api.github.com/repos/SeeedDocument/"))
        self.assertIsNone(github_file(book.replace("SeeedDocument","third-party")))
        self.assertEqual(kind(book.replace("Compatibility%20List","Power%20Consumption")),"reference")

    def test_supported_card_and_host_urls_must_be_exact_and_the_kit_is_a_separate_sku(self):
        device="https://www.seeedstudio.com/reComputer-J4012-w-o-power-adapter-p-5628.html"
        raw="sku: 114993556,E24121001\n"+compatibility.NIC+"\n## Supported Devices\n- [reComputer J4012]("+device+")\n## Other models\n- [reComputer J9999](https://www.seeedstudio.com/other-p-9.html)"
        record=compatibility.wiki_facts(compatibility.WIFI,raw,"https://github.com/Seeed-Studio/wiki-documents/blob/revision/wiki.md")
        hosts={"110110184":{"sku":"110110184","name":"reComputer J4012 (w/o power adapter)","url":device},
               "110110191":{"sku":"110110191","name":"reComputer J4012","url":device+"-different"},
               "114993556":{"sku":"114993556","name":"RTL8822CE Wireless NIC","url":compatibility.NIC},
               "E24121001":{"sku":"E24121001","name":"RTL8822CE Wireless NIC Kits","url":"https://www.seeedstudio.com/kit.html"}}
        result=compatibility.card_hosts(record,hosts)
        self.assertEqual(list(result),["110110184"])
        self.assertEqual(result["110110184"][0]["sku"],"114993556")
        self.assertTrue(result["110110184"][0]["source"].endswith("#L4"))
        hosts["110110191"]["url"]=device
        self.assertEqual(list(compatibility.card_hosts(record,hosts)),["110110184"])
        hosts["110110191"]["name"]="reComputer J4012 (w/o power adapter) duplicate"
        self.assertFalse(compatibility.card_hosts(record,hosts))

    def test_module_matrix_preserves_pin_caveat_and_never_lends_an_old_version_its_parts(self):
        header={"A":"Grove Modules","B":"SKU","C":"Retail Price","D":"Category","E":"Port","I":"MakeCode Package Developed"}
        cells=[(1,header)]
        for n in range(2,52):
            cells.append((n,{"A":"Grove module "+str(n),"B":str(100000000+n),"C":"12.50","E":"Digital","I":"No(please use the PIN block)"}))
        summary,rows=sheets.structured_sheet("Sheet1",cells)
        record={"sha256":sheets.MATRICES[sheets.MICROBIT_URL][0],"sheetRows":rows,"worksheets":[summary]}
        host={"sku":"103100063","name":"Grove Shield for micro:bit v2.0"}
        self.assertFalse(sheets.verified_rows(sheets.MICROBIT_URL,{**host,"sku":"103030195"},record,{}))
        facts=sheets.verified_rows(sheets.MICROBIT_URL,host,record,{})
        merge_rows(host,facts,{})
        self.assertEqual(len(host["accessories"]),50)
        first=host["accessories"][0]
        self.assertEqual((first["type"],first["publishedSku"],first["sku"]),("Official module list","100000002",""))
        self.assertEqual(first["compatibilityDetails"][0]["makeCode"],"No(please use the PIN block)")
        self.assertEqual(first["compatibilityDetails"][0]["cellRange"],"A2:I2")
        self.assertNotIn("price",first)
