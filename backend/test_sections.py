import unittest

from .extract import column_rows,install_column,text_link
from .updates import refresh_facts


URL="https://www.seeedstudio.com/reComputer-R1014-10-p-6961.html"


def table(rows):
    return "<table>"+"".join("<tr>"+"".join("<td>"+cell+"</td>" for cell in cells)+"</tr>" for cells in rows)+"</table>"


class SectionsTest(unittest.TestCase):
    def test_another_product_family_promo_and_assembled_quantity(self):
        from .storefront import normalized
        raw="<p>Seeed provides customization service based on BeagleBone series boards.</p><h2>Part List</h2><ul><li>Antenna x 2 (Assembled)</li><li>Heat Sink (Assembled)</li></ul>"
        row={"sku":"110991565","name":"Odyssey Blue","url_key":"odyssey","url_suffix":".html","description":{"html":raw}}
        current=normalized(row,{})
        self.assertEqual(current["notes"],[])
        self.assertEqual(current["parts"],[["Antenna (Assembled)","2"],["Heat Sink (Assembled)",""]])
        self.assertIn("Antenna%20x%202",current["partSources"]["Antenna (Assembled)"])
        row["description"]["html"]=raw.replace("x 2","x 3")
        merged=refresh_facts(current,normalized(row,{}),None,{})
        self.assertEqual(merged["parts"][0],["Antenna (Assembled)","3"])
        row["name"]="Seeed Studio BeagleBone Green"
        self.assertTrue(normalized(row,{})["notes"])

    def test_short_description_includes_active_omission_but_not_fees_or_sample_code(self):
        from .storefront import normalized
        row={"sku":"114993667","name":"Motor kit","url_key":"kit","url_suffix":".html",
             "description":{"html":""}, "short_description":{"html":"<p>Shipping and VAT are not included.</p>"
                 "<p>This example does not include the motor control interface.</p>"
                 "<p>The Motor Kit does not include 3D-printed parts and camera.</p>"}}
        notes=normalized(row,{})["notes"]
        self.assertEqual([n["text"] for n in notes],["The Motor Kit does not include 3D-printed parts and camera."])
        self.assertEqual(notes[0]["location"],"short_description")
        self.assertIn("#:~:text=",notes[0]["source"])
        row["short_description"]["html"]="<p>This price does not include taxes.</p><p>The board does not come with a cable.</p>"
        self.assertEqual([n["text"] for n in normalized(row,{})["notes"]],["The board does not come with a cable."])
    def test_optional_product_family_must_match_the_caption_and_statement(self):
        from .extract import body_options,tree
        lead="<p>Optionally, enhance your kit with various SenseCAP S210x LoRaWAN® Sensors.</p><p>More detail:</p>"
        caption="<p>The following table shows the details of the SenseCAP S210x LoRaWAN® Sensor:</p>"
        grid=table([["SKU","Product"],["114992867","S2101"],["114992868","S2102"],["101990962","A1101"]])
        options=body_options(tree(lead+caption+grid),URL)
        self.assertEqual([r["sku"] for r in options],["114992867","114992868"])
        self.assertIn("Optionally",options[0]["basisText"])
        self.assertEqual(body_options(tree(lead+caption.replace("S210x","M200")+grid),URL),[])

    def test_measurement_exclusions_do_not_become_accessory_purchases(self):
        from .extract import facts,measurement_exclusion_only,tree
        for statement in ("Weight 33g (power adaptor not included)",
                          "Dimension 143.6x135x34mm (connector not included) 150.6x135x34mm (connector included)",
                          "Operating Temperature 0 to +50 °C (measurement range of CO2) -40 to +85 °C (CO2 module not included)"):
            self.assertTrue(measurement_exclusion_only(statement))
            self.assertEqual(facts(tree("<p>"+statement+"</p>"),URL),[])
        for statement in ("19V Power Adapter (Barrel Jack 5.5mm, Power cord not included) x1",
                          "Tested with the 3.5mm jack. Speaker not included.",
                          "Weight 33g. Power adapter is sold separately.",
                          "Weight 33g, cable not included in the kit."):
            self.assertFalse(measurement_exclusion_only(statement))
            self.assertTrue(facts(tree("<p>"+statement+"</p>"),URL))

    def test_repeated_component_in_two_categories_is_quoted_with_unresolved_total(self):
        from .storefront import normalized
        article="<h2>Part List</h2>"+table([
            ["Category","Module","Amount"],["Input","Grove - Rotary Angle Sensor","x1"],
            ["LED","Grove - Red LED","x1"],["Sensor","Grove - Rotary Angle Sensor","x1"]])
        row={"sku":"123","name":"Grove Creator Kit","url_key":"kit","url_suffix":".html","description":{"html":article}}
        current=normalized(row,{})
        merged=refresh_facts({},current,None,{})
        self.assertEqual(merged["parts"],[["Grove - Rotary Angle Sensor",""],["Grove - Red LED","x1"]])
        evidence=merged["partDescriptions"]["Grove - Rotary Angle Sensor"]
        self.assertEqual(evidence["groups"],[{"group":"Input","quantity":"x1"},{"group":"Sensor","quantity":"x1"}])
        self.assertEqual(evidence["kind"],"crossListed")
        self.assertNotIn("_bodyCrossListed",merged)

    def test_line_breaks_and_prefix_counts_use_the_actual_packing_markup(self):
        from .extract import section_parts,tree
        heading="<h2>Parts List</h2>"
        raw="<p>1 x TF-Luna LiDAR Module <br>1 x <b>6-Pin</b> Communication Cable</p>"
        expected=[["TF-Luna LiDAR Module","1"],["6-Pin Communication Cable","1"]]
        self.assertEqual(section_parts(tree(heading+raw)),expected)
        self.assertEqual(column_rows(heading+raw,URL)["parts"],expected)
        raw="<ul><li>x2 P6200 probes</li><li>x1 Carrying Case</li><li>X2 Expansion Board</li></ul>"
        self.assertEqual(section_parts(tree(heading+raw)),[["P6200 probes","2"],["Carrying Case","1"],["X2 Expansion Board",""]])
        wrapped="<p>1 x <b>Adapter</b><br>with USB cable</p>"
        self.assertEqual(section_parts(tree(heading+wrapped)),[["Adapter with USB cable","1"]])

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
