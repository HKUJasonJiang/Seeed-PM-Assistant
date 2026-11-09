"""Regression checks for SKU-vs-family quantities and citations."""
import copy
import unittest

from .r1000_evidence import ASSEMBLY, MANUAL, enrich_r1000


class R1000EvidenceTest(unittest.TestCase):
    def sample(self):
        return {"sku":"100025879", "name":"reComputer R1014-10 - Raspberry Pi IoT Gateway",
                "url":"https://www.seeedstudio.com/reComputer-R1014-10-p-6961.html",
                "docs":[{"name":"User Manual","url":MANUAL}], "parts":[], "partStatus":"empty"}

    def test_partial_package_is_explicit_and_idempotent(self):
        p = enrich_r1000(self.sample())
        parts = dict(p["parts"])
        self.assertEqual(p["storePartStatus"], "empty")
        self.assertEqual(p["partEvidenceScope"], "family")
        self.assertEqual(parts["DIN-rail clip"], "")
        self.assertEqual(parts["DIN-rail installation screws"], "")
        self.assertEqual(parts["120 Ω RS485 termination resistor"], "5")
        self.assertEqual(p["partSources"]["120 Ω RS485 termination resistor"], MANUAL+"#page=18")
        accessories = {a["sku"]: a for a in p["accessories"]}
        self.assertEqual(len(accessories), 25)
        self.assertIn("SPI", accessories["114993268"]["name"])
        self.assertIn("USB", accessories["114992628"]["name"])
        self.assertEqual(accessories["110992005"]["source"], MANUAL+"#page=48")
        self.assertEqual(p["customUrl"], ASSEMBLY)
        self.assertEqual(enrich_r1000(copy.deepcopy(p)), p)

    def test_existing_sku_packing_list_preserves_its_counts(self):
        p = self.sample()
        p.update(parts=[["DIN-rail clip", "x 1"], ["Screw Pack", "x 1"], ["120Ω Resistor", "x 5"]],
                 partStatus="present")
        before = copy.deepcopy(p["parts"])
        enrich_r1000(p)
        self.assertEqual(p["parts"], before)
        self.assertEqual(p["partSources"], {})
        self.assertEqual(p["storePartStatus"], "present")

    def test_exact_title_specs_keep_original_attributes(self):
        p = self.sample()
        p["name"] += " | 2GB RAM, 16GB eMMC"
        p["attributes"] = [["Processor", "Compute Module 4"]]
        self.assertEqual(enrich_r1000(p)["modelSpecs"], [
            {"name": "RAM", "value": "2GB", "source": p["url"]},
            {"name": "Storage", "value": "16GB eMMC", "source": p["url"]}])
        self.assertEqual(p["attributes"], [["Processor", "Compute Module 4"]])
        p["name"] = p["name"].replace("2GB RAM", "up to 4GB RAM")
        self.assertEqual(enrich_r1000(p)["modelSpecs"], [])

    def test_multiple_choices_and_wrong_sources_leave_specs_empty(self):
        for tail in ("| 2GB/4GB RAM, 16GB eMMC", "| 2GB RAM, optional 16GB eMMC",
                     "or R1024-10 | 2GB RAM, 16GB eMMC", "options | 2GB RAM, 16GB eMMC",
                     "| 2GB RAM, 16GB eMMC / 32GB eMMC", "| 2GB RAM", ""):
            with self.subTest(tail=tail):
                p = self.sample()
                p["name"] += " " + tail
                self.assertEqual(enrich_r1000(p)["modelSpecs"], [])
        p = self.sample()
        p["name"] += " | 2GB RAM, 16GB eMMC"
        p["url"] = p["url"].replace("R1014-10", "R1036-10")
        self.assertEqual(enrich_r1000(p)["modelSpecs"], [])

    def test_accessories_and_other_families_do_not_inherit_the_facts(self):
        for name in ("reComputer R1125-10", "PoE module kit for reComputer R1000",
                     "reComputer R1014-10 accessory bundle"):
            p = {**self.sample(), "name":name}
            before = copy.deepcopy(p)
            self.assertEqual(enrich_r1000(p), before)
        future = {**self.sample(), "sku":"test-new", "name":"reComputer R1099-10 new unit", "docs":[]}
        self.assertNotIn("accessories", enrich_r1000(future))


if __name__ == "__main__":
    unittest.main()
