"""Regression checks use invented local documents only."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from .internal_knowledge import InternalKnowledge, import_directory
from .storage import CATALOG_PREFIX, Store, packed
from .chat_context import product_sources
from .assistant import cited_reply

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def fixture_workbook(path):
    rows = {
        1: {"B":"SKU", "C":"名称", "O":"SKU", "P":"名称"},
        2: {"A":"Archive family (EOL)","B":"900000001","C":"Fixture board","F":"EOL",
            "G":"PRIVATE_COST_DO_NOT_IMPORT","O":"900000002","P":"StereoLabs Fixture"},
        3: {"B":"900000003","C":"Fixture board 3"},
        4: {"A":"Active family","B":"900000004","C":"Fixture board 4"}}
    sheet = '<worksheet xmlns="'+NS+'"><sheetData>'
    for row, cols in rows.items():
        sheet += '<row r="'+str(row)+'">'+''.join('<c r="'+col+str(row)+'" t="inlineStr"><is><t>'+text+'</t></is></c>' for col,text in cols.items())+'</row>'
    sheet += '</sheetData><mergeCells><mergeCell ref="A2:A3"/></mergeCells></worksheet>'
    with zipfile.ZipFile(path,"w") as z:
        z.writestr("xl/workbook.xml",'<workbook xmlns="'+NS+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Catalogue 20260101" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",'<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml",sheet)


class InternalKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root/"sources"
        self.source.mkdir()
        self.local = self.root/"private"
        self.local.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_bounded_merged_categories_and_price_exclusion(self):
        fixture_workbook(self.source/"input.xlsx")
        data = import_directory(self.source)
        ids = {sku for r in data["records"] if r["kind"]=="eol" for sku in r["skus"]}
        self.assertEqual(ids,{"900000001","900000003"})
        self.assertNotIn("PRIVATE_COST_DO_NOT_IMPORT",json.dumps(data))
        self.assertIn("StereoLabs Fixture",json.dumps(data))
        self.assertTrue(any("B3/C3" in r["location"] for r in data["records"]))

    def test_unchecked_eol_option_in_pcn_is_not_discontinuation(self):
        body = """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
        <w:p><w:r><w:t>CHANGE DESCRIPTION</w:t></w:r></w:p>
        <w:p><w:r><w:t>☐ End of Life</w:t></w:r></w:p>
        <w:p><w:r><w:t>☑ Electrical change</w:t></w:r></w:p>
        <w:p><w:r><w:t>REASONS FOR CHANGE</w:t></w:r></w:p>
        <w:p><w:r><w:t>Connector revision.</w:t></w:r></w:p>
        <w:tbl><w:tr><w:tc><w:p><w:r><w:t>900000001</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Fixture</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        </w:body></w:document>"""
        file = self.source/"PCN20260101-001.docx"
        with zipfile.ZipFile(file,"w") as archive:
            archive.writestr("word/document.xml",body)
        records = import_directory(self.source)["records"]
        self.assertTrue(records)
        self.assertFalse(any(r["kind"]=="eol" for r in records))
        with zipfile.ZipFile(file,"w") as archive:
            archive.writestr("word/document.xml",body.replace("☐ End of Life","☑ End of Life"))
        self.assertTrue(any(r["kind"]=="eol" for r in import_directory(self.source)["records"]))

    def test_exact_host_ssd_policy_and_preserve_failed_source(self):
        file = self.source/"host.md"
        file.write_text("# Fixture host\n\n- 销售SKU：900000001\n\n## 存储\n\n1个 M.2 NVMe 2280 系统盘。SSD升级为1TB默认替换标配128GB。\n\n1TB工业级/商业级须明确。",encoding="utf8")
        knowledge = InternalKnowledge(self.local)
        knowledge.load(self.source)
        catalogue = {"products":[{"sku":"900000001","name":"Public fixture"}]}
        knowledge.apply(catalogue)
        result = knowledge.assess(["900000001"],"SSD升级为1TB")[0]
        self.assertTrue(any("128GB" in x for x in result["actions"]))
        self.assertFalse(any("原盘是否保留" in x for x in result["confirmations"]))
        self.assertTrue(any("商业级" in x for x in result["confirmations"]))
        result = knowledge.assess(["900000001"],"加装1TB SSD，保留原盘")[0]
        self.assertTrue(any("目标盘位" in x for x in result["confirmations"]))
        self.assertFalse(any("替换标配" in x for x in result["actions"]))
        result = knowledge.assess(["900000001"],"SSD升级为2TB工业级")[0]
        self.assertTrue(any("2TB" in x and "128GB" in x for x in result["actions"]))
        self.assertFalse(result["confirmations"])
        before = knowledge.data["records"]
        file.write_bytes(b"\xffbad")
        knowledge.load()
        knowledge.apply(catalogue)
        self.assertTrue(knowledge.summary()["errors"])
        self.assertEqual(knowledge.data["records"],before)
        self.assertIn("900000001",knowledge.products)

    def test_confirmed_dual_drive_request_does_not_repeat_questions(self):
        (self.source/"ssd.md").write_text("# SSD\n|Fixture dual drive host|900000001|双SSD设计：2个M.2 NVMe 2280位|\n",encoding="utf8")
        knowledge = InternalKnowledge(self.local)
        knowledge.load(self.source)
        knowledge.apply({"products":[]})
        result = knowledge.assess(["900000001"],"SSD盘1换1TB工业级，盘2保留256GB")[0]
        self.assertFalse(result["confirmations"])
        self.assertTrue(any("盘1" in x for x in result["actions"]))
        self.assertTrue(any("盘2" in x for x in result["actions"]))
        self.assertEqual(knowledge.assess(["900000001"],"仅改Logo"),[])

    def test_candidate_grade_is_separate_from_customer_requirement(self):
        knowledge = InternalKnowledge(self.local)
        source = {"sourceId":"fixture","location":"A1","version":"fixture","kind":"identity","skus":[]}
        knowledge.products = {
            "900000001":{"sku":"900000001","name":"Host","eol":False,"records":[{"kind":"ssd","title":"SSD","text":"1个M.2 NVMe 2280；标配128GB，升级默认替换。"}]},
            "900000002":{"sku":"900000002","name":"2TB SSD","names":[],"eol":False,"records":[{**source,"productName":"2TB NVMe SSD 2280"}]},
            "900000003":{"sku":"900000003","name":"Commercial SSD","names":[],"eol":False,"records":[{**source,"productName":"2TB commercial NVMe SSD 2280"}]}}
        result = knowledge.assess(["900000001"],"SSD升级为2TB工业级")[0]
        self.assertEqual([c["sku"] for c in result["candidates"]],["900000002"])
        self.assertEqual(result["candidates"][0]["gradeStatus"],"unconfirmed")
        self.assertTrue(any("资格尚待核实" in x for x in result["confirmations"]))
        self.assertFalse(any("请明确商业级" in x for x in result["confirmations"]))

    def test_source_change_applies_without_public_rewrite(self):
        file = self.source/"ssd.md"
        file.write_text("# SSD\n|Fixture host|900000001|M.2 NVMe 2242|\n",encoding="utf8")
        (self.root/"data").mkdir()
        catalog = {"products":[{"sku":"900000001","name":"Public fixture","url":""}]}
        raw = CATALOG_PREFIX.encode()+packed(catalog)+b";"
        (self.root/"data/catalog.js").write_bytes(raw)
        store = Store(self.local,self.root)
        store.internal.load(self.source)
        initial = store.public()
        self.assertIn("2242",str(initial["internalProducts"]["900000001"]))
        file.write_text("# SSD\n|Fixture host|900000001|M.2 NVMe 2280|\n",encoding="utf8")
        self.assertIn("2280",str(store.public()["internalProducts"]["900000001"]))
        self.assertEqual((self.root/"data/catalog.js").read_bytes(),raw)
        self.assertNotIn("internal",str(store.catalog))
        store.commit_catalog({"products":[{"sku":"900000001","name":"New public name","url":""}]})
        self.assertIn("2280",str(store.public()["internalProducts"]["900000001"]))
        self.assertEqual(store.effective("900000001")["name"],"New public name")

    def test_only_selected_internal_context_and_validated_citation(self):
        (self.source/"rules.md").write_text("# SSD\n|Host A|900000001|2280|\n|Host B|900000002|2242 unrelated-private-marker|",encoding="utf8")
        (self.root/"data").mkdir()
        (self.root/"data/catalog.js").write_bytes(CATALOG_PREFIX.encode()+packed({"products":[]})+b";")
        store = Store(self.local,self.root)
        store.internal.load(self.source)
        store.public()
        result = product_sources(store,"900000001","zh","SSD升级","accessories",[])
        self.assertTrue(result)
        self.assertEqual(result[0]["kind"],"internal")
        self.assertNotIn("unrelated-private-marker",str(result))
        self.assertEqual(store.effective("900000001")["name"],"Host A")
        result[0]["id"] = 1
        reply = cited_reply('{"points":[{"text":"Fixture claim","refs":[1]}]}',result,"fake","fake")
        self.assertEqual(reply["sources"][0]["sourceId"],result[0]["sourceId"])
        self.assertEqual(reply["sources"][0]["location"],result[0]["location"])


if __name__ == "__main__":
    unittest.main()
