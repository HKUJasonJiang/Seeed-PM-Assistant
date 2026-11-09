import unittest

from .product_specs import install_description_specs,install_reference_sections,install_specification


class StoreSpecificationTests(unittest.TestCase):
    def setUp(self):
        self.product = {"url": "https://www.seeedstudio.com/model-p-123.html"}

    def test_model_comparison_retains_header_and_merged_cells(self):
        install_specification(self.product, """
          <table><caption>Series comparison</caption><tr><th></th><th>A</th><th>B</th></tr>
          <tr><td>RAM</td><td>2 GB</td><td>8 GB</td></tr>
          <tr><td>Power</td><td colspan="2">12 V</td></tr></table><p>Check your model.</p>
        """)
        table, = self.product["specTables"]
        self.assertEqual(table["title"], "Series comparison")
        self.assertEqual(table["rows"][0][2], {"text": "B", "header": True})
        self.assertEqual(table["rows"][1], ["RAM", "2 GB", "8 GB"])
        self.assertEqual(table["rows"][2][1], {"text": "12 V", "colspan": 2})
        self.assertEqual(self.product["specText"], ["Check your model."])
        self.assertTrue(self.product["specSource"].startswith(self.product["url"]))
        self.assertNotIn("attributes", self.product)

    def test_empty_image_and_unparsed_fields_are_distinguishable(self):
        install_specification(self.product, "<div><img src='dimensions.jpg'></div>")
        self.assertEqual(self.product["specStatus"], "image")
        install_specification(self.product, "<p>" + "x" * 500 + "</p>")
        self.assertEqual(self.product["specStatus"], "unparsed")
        install_specification(self.product, "<p><br></p><script>123</script>")
        self.assertEqual(self.product["specStatus"], "empty")
        self.assertNotIn("specRowsOmitted", self.product)

    def test_previous_section_cleared_only_on_explicit_replacement(self):
        install_specification(self.product, "<p>2 ports</p>")
        install_specification(self.product, "")
        self.assertNotIn("specText", self.product)
        self.assertNotIn("specSource", self.product)
        self.assertEqual(self.product["specStatus"], "empty")

    def test_description_heading_isolated_from_following_packlist(self):
        install_description_specs(self.product,"<p><b>Technical Specifications</b></p><table><tr><td>USB</td><td>2</td></tr></table><h2>Part List</h2><ul><li>Cable x 1</li></ul>")
        self.assertEqual(self.product["specLocation"],"description")
        self.assertEqual(self.product["specTables"][0]["rows"],[["USB","2"]])
        fresh = {"url":self.product["url"]}
        install_description_specs(fresh,"<h2>Specifications</h2><div><h3>Part List</h3><ul><li>Cable</li></ul></div>")
        self.assertNotIn("specTables",fresh)

    def test_dedicated_technical_specifications_take_precedence(self):
        install_specification(self.product,"<p>Separate model-specific facts</p>")
        install_description_specs(self.product,"<h2>Specification</h2><ul><li>Series listing</li></ul>")
        self.assertEqual(self.product["specText"],["Separate model-specific facts"])
        self.assertNotIn("specLocation",self.product)

    def test_supplemental_technical_and_classification_tables_stay_separate(self):
        install_reference_sections(self.product,{"certification_info_tech":"<table><tr><td>Dimensions</td><td>0mm x0mm x0mm</td></tr></table>","certification_info_eccn":"<table><tr><td>ECCN</td><td>EAR99</td></tr></table>"})
        extras=self.product["referenceSections"]
        self.assertTrue(extras["certification_info_tech"]["tables"][0]["rows"][0][1]["unconfirmed"])
        self.assertEqual(extras["certification_info_eccn"]["tables"][0]["rows"][0],["ECCN","EAR99"])
        install_reference_sections(self.product,{"certification_info_tech":""})
        self.assertNotIn("certification_info_tech",self.product["referenceSections"])
        self.assertIn("certification_info_eccn",self.product["referenceSections"])
