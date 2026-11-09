import unittest

from .extract import column_rows,install_column,text_link
from .updates import refresh_facts


URL="https://www.seeedstudio.com/reComputer-R1014-10-p-6961.html"


def table(rows):
    return "<table>"+"".join("<tr>"+"".join("<td>"+cell+"</td>" for cell in cells)+"</tr>" for cells in rows)+"</table>"


class SectionsTest(unittest.TestCase):
    def test_product_metadata_is_not_packing(self):
        labels=["Product Type","Categories","Sensors","Series","RAM","Storage","Operating System","Network"]
        values=["Device","Computer","Light、Humidity","RaspberryPi","2GB","16GB","Raspbian, Ubuntu, Debian","Wi-Fi、LoRa/LORaWan、Bluetooth"]
        result=column_rows(table(zip(labels,values)),URL)
        self.assertEqual(result["parts"],[])
        self.assertEqual(result["storePartStatus"],"empty")
        self.assertEqual([(r["name"],r["value"]) for r in result["attributes"]],list(zip(labels,values)))
        self.assertTrue(all(r["source"].startswith(URL+"#:~:text=") for r in result["attributes"]))

    def test_package_versus_conditional_items(self):
        data=table([["Parts Name","Quantity"],["Power adapter (power cord not included)","x1"],["Wall mount bracket (not included)","1"]])
        data+="<p>Purchased before March 2025</p>"+table([["Old cable","3"]])
        got=column_rows(data,URL)
        self.assertEqual(got["parts"],[["Power adapter (power cord not included)","x1"]])
        self.assertIn(["Purchased before March 2025","Old cable","3"],got["unclassifiedRows"])
        self.assertIn(["Wall mount bracket (not included)","1"],got["unclassifiedRows"])

    def test_dedicated_field_preserves_real_description(self):
        current={"url":URL,"parts":[["Terminal block","2"]],"partSources":{"Terminal block":text_link(URL,"Terminal block")}}
        install_column(current,table([["Screws","4"]]))
        self.assertEqual(current["parts"],[["Screws","4"],["Terminal block","2"]])
        install_column(current,"")
        self.assertEqual(current["parts"],[["Terminal block","2"]])
        self.assertEqual(current["storePartStatus"],"empty")

    def test_older_preview_cannot_clear_new_knowledge_on_failure(self):
        previous={"url":URL,"details":False,"parts":[["DIN clip",""]],"partScopes":{"DIN clip":"family"}}
        install_column(previous,table([["RAM","2GB"],["Network","Wi-Fi"]]))
        old_pending={"url":URL,"parts":[],"notes":[],"docs":[],"wikiLinks":[],"details":False}
        refreshed=refresh_facts(previous,old_pending,[],{})
        for k in ("parts","attributes","partScopes","attributeSource","attributeChecked","storePartStatus"):
            self.assertEqual(previous[k],refreshed[k])
        # A newly read, explicitly empty field legitimately replaces old storefront attributes.
        install_column(old_pending,"<p></p>")
        refreshed=refresh_facts(previous,old_pending,[],{})
        self.assertEqual(refreshed["attributeStatus"],"empty")
        self.assertEqual(refreshed["attributes"],[])

    def test_malformed_nonempty_is_distinct_from_empty(self):
        got=column_rows(table([["Reachy Mini Lite","Reachy Mini Wireless"],["None","Includes battery"]]),URL)
        self.assertEqual(got["storePartStatus"],"unparsed")
        self.assertEqual(got["unclassifiedRows"][1],["None","Includes battery"])
        self.assertEqual(column_rows("<p><img src='x'></p>",URL)["partStatus"],"unparsed")
        self.assertEqual(column_rows(None,URL)["attributeStatus"],"empty")


if __name__=="__main__":unittest.main()
