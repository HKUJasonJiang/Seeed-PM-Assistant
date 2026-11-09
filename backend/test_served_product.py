"""The ordinary storefront may serve one of two HTML templates at a product URL."""
import json
import unittest
from unittest.mock import Mock, patch

from .bulk_catalog import read_public_detail
from .storage import Problem
from .storefront import DETAIL_FIELDS, DetailIdentity, OfficialStore


def storefront_page(sku="104990222", json_sku="104990222", omit=(), visible=False):
    text="<table><tr><td>尺寸</td><td>Ø25 mm</td></tr></table>"
    product={"name":"PiShow","sku":sku,"id":458,"product_stage":"EOL",
             "items":[{"product":{"id":112,"sku":"COMPONENT","name":"Bundled part"}}],
             **dict.fromkeys(DETAIL_FIELDS,None)}
    product.update(specification="$2b",documents="$f0",faq_list=[{"answer":"$$3.50"}])
    for key in omit:product.pop(key)
    view=["$","section",None,{"deviceType":"desktop","product":product}]
    parts=[':HL["/app.css","style"]\n','2b:T'+format(len(text.encode("utf-8")),"x")+','+text,
           "6:"+json.dumps(view,ensure_ascii=False)+"\n"]
    scripts="".join("<script>self.__next_f.push("+json.dumps([1,p],ensure_ascii=False)+")</script>" for p in parts)
    primary=("<div>SKU <!-- -->"+json_sku+"</div>" if visible else
             '<script type="application/ld+json">'+json.dumps({"@type":"Product","sku":json_sku})+'</script>')
    return ("<html><body>"+primary+scripts+"</body></html>").encode("utf-8")


class ServedProductTest(unittest.TestCase):
    def test_exact_primary_sku_unicode_section_and_lifecycle(self):
        fields=OfficialStore.detail_payload(storefront_page(),"104990222")
        OfficialStore.verify_entity_id(fields,458)
        self.assertEqual(fields["_verifiedStoreId"],"458")
        self.assertEqual(fields["_storeLifecycle"],"EOL")
        self.assertEqual(fields["_pageTemplate"],"storefront_app")
        self.assertIn("尺寸",fields["specification"])
        self.assertEqual(fields["faq_list"],[{"answer":"$3.50"}])
        self.assertIsNone(fields["certification_info_part"])
        self.assertNotIn("documents",fields)  # An unresolved text reference.
        self.assertNotIn("addons",fields)
        with self.assertRaises(DetailIdentity):OfficialStore.verify_entity_id(fields,99)

    def test_visible_sku_fallback_missing_data_and_nested_component(self):
        raw=storefront_page(visible=True,omit=("specification",))
        self.assertNotIn("specification",OfficialStore.detail_payload(raw,"104990222"))
        with self.assertRaises(DetailIdentity) as mismatch:OfficialStore.detail_payload(raw,"COMPONENT")
        self.assertEqual(mismatch.exception.observed,{"reason":"different_displayed_sku","displayedSkus":["104990222"]})

    def test_display_and_held_product_must_agree(self):
        raw=storefront_page(sku="BUNDLE",json_sku="LEGACY")
        with self.assertRaises(DetailIdentity) as mismatch:OfficialStore.detail_payload(raw,"LEGACY")
        self.assertEqual(mismatch.exception.observed["displayedSkus"],["BUNDLE"])

    def test_access_challenge_delivered_as_successful_html_stops(self):
        raw=b"<html><title>Just a moment...</title><script>window.cf_chl_opt = {};</script></html>"
        with self.assertRaises(Problem) as error:OfficialStore.detail_payload(raw,"A")
        self.assertEqual(error.exception.code,"STORE_ACCESS_CHALLENGE")
        with self.assertRaises(DetailIdentity):OfficialStore.detail_payload(b"<html><title>Access Control module</title></html>","A")
        with self.assertRaises(Problem) as empty:OfficialStore.detail_payload(b"", "A")
        self.assertEqual(empty.exception.code, "DETAIL_LAYOUT_UNKNOWN")

    def test_transport_retries_once_and_access_challenges_never_retry(self):
        remote = Mock()
        remote.detail.side_effect = [Problem("STORE_UNREACHABLE",502), {"_verifiedStoreId":"458"}]
        with patch("backend.bulk_catalog.time.sleep") as pause, patch("builtins.print"):
            self.assertEqual(read_public_detail(remote, "http://unused.invalid", "A")["_verifiedStoreId"], "458")
            pause.assert_called_once_with(60)
        remote.reset_mock()
        remote.detail.side_effect = Problem("STORE_ACCESS_CHALLENGE",403)
        with self.assertRaises(Problem), patch("backend.bulk_catalog.time.sleep") as pause:
            read_public_detail(remote, "http://unused.invalid", "A")
        remote.detail.assert_called_once()
        pause.assert_not_called()


if __name__=="__main__":unittest.main()
