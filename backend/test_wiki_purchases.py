import unittest

from .wiki_purchases import application_guide,declared_skus,documented_component,markdown_meta,matches_model,primary_purchases,same_declared_product


class WikiPurchaseTests(unittest.TestCase):
    def test_reads_editorial_purchase_button_before_other_components(self):
        body='''
        <a class="get_one_now_item" href="https://www.seeedstudio.com/Grove-Thing-p-123.html?src=wiki">Get One Now</a>
        <a href="https://www.seeedstudio.com/Wrong-p-7.html">Kit example</a>
## Hardware Requirements
        [![shop](https://files.seeedstudio.com/Get_One_Now.jpg)](https://www.seeedstudio.com/Other-p-4.html)
        '''
        self.assertEqual(primary_purchases(body),{"/grove-thing-p-123.html"})

    def test_requires_exact_host_and_declared_wiki_slug(self):
        body='[![shop](https://files.seeedstudio.com/Get_One_Now.jpg)](https://www.seeedstudio.com.cn/Kit-p-123.html)'
        self.assertFalse(primary_purchases(body))
        self.assertIsNone(markdown_meta("---\ntitle: Example\n---\nBody"))
        self.assertEqual(markdown_meta("---\ntitle: Example\nslug: /Some_Kit\n---\nBody")[:2],("Example","https://wiki.seeedstudio.com/Some_Kit/"))

    def test_adjacent_model_does_not_match(self):
        self.assertFalse(matches_model("Getting started with reComputer J4012","reComputer J4011 Kit"))
        self.assertTrue(matches_model("RS485 500cm Ultrasonic Level Sensor","RS485 500cm Ultrasonic Level Sensor"))

    def test_application_training_guide_with_a_product_purchase_button(self):
        self.assertTrue(application_guide("Cloud_Chain/SenseCraft_Robotics/guides/so_arm.md","SO-ARM101 Training Guide"))
        self.assertTrue(application_guide("Robotics/Robot_Kits/Lerobot/motors.md","SO-Arm LeRobot Tutorial"))
        self.assertFalse(application_guide("Hardware/Jetson/J4012.md","Getting Started with reComputer J4012"))

    def test_explicit_metadata_is_not_a_component_list_in_the_article(self):
        text="---\ntitle: Board\nsku: 102010001, E23010807\n---\nAdditional SKU: 999999991"
        self.assertEqual(declared_skus(text),({"102010001","E23010807"},3))
        self.assertEqual(declared_skus("---\nsku:\n  - '100025879'\n  - 110110145\n---\n"),({"100025879","110110145"},2))
        self.assertFalse(same_declared_product("Edge Devices Powered by RockChip","reRouter CM4 1432 Raspberry Pi"))
        self.assertFalse(same_declared_product("WM1302 Pi Hat for Raspberry Pi","Wio-WM1302 LoRaWAN Gateway Module (USB)"))
        self.assertTrue(same_declared_product("WM1302 Pi Hat for Raspberry Pi","WM1302 Raspberry Pi Hat"))
        source="---\ndescription: This guide documents the J501 carrier board.\nsku: 100020039\n---\n"
        self.assertTrue(documented_component(source,"Mini J501 interfaces","reComputer Mini J501 Carrier Board for Jetson AGX Orin with GMSL Extension"))
