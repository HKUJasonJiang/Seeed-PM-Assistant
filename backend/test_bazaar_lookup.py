import unittest
from .bazaar_lookup import check_accessory, search_term
from .storage import Problem
from .storefront import RateLimit
from .accessory_checks import attach_checks


class Source:
    def __init__(self,items=(),error=None):
        self.items=list(items);self.error=error;self.calls=[]
    def public_query(self,query,variables):
        self.calls.append(variables)
        if self.error:raise self.error
        return {"products":{"items":self.items,"total_count":len(self.items)}}


def row(sku,name,key="module"):
    return {"sku":sku,"name":name,"url_key":key,"url_suffix":".html"}


class BazaarLookupTests(unittest.TestCase):
    def test_refresh_attaches_public_check_without_repeating_fresh_query(self):
        remote=Source([row("111111111","Precise accessory","precise-accessory")])
        product={"accessories":[{"name":"Precise accessory","source":"https://wiki.seeedstudio.com/fixture/"}]}
        cache={}
        attach_checks(product,{},remote,cache)
        self.assertEqual(product["accessories"][0]["bazaarCheck"]["status"],"confirmed")
        calls=len(remote.calls)
        attach_checks(product,{},remote,cache)
        self.assertEqual(len(remote.calls),calls)

    def test_refresh_stops_on_rate_limit_and_retains_resume_record(self):
        remote=Source(error=RateLimit(9999999999))
        cache={}
        with self.assertRaises(RateLimit):
            attach_checks({"accessories":[{"name":"Fixture accessory"}]}, {},remote,cache)
        self.assertEqual(next(iter(cache.values()))["status"],"rate_limited")

    def test_optional_lookup_error_preserves_old_match_and_skips_more_requests(self):
        previous={"status":"confirmed","checkedAt":"2020-01-01T00:00:00+00:00",
                  "match":{"sku":"111111111","url":"https://www.seeedstudio.com/fixture.html"}}
        product={"accessories":[{"name":"Fixture 1","bazaarCheck":previous},{"name":"Fixture 2"}]}
        remote=Source(error=Problem("STORE_HTTP_503"))
        attach_checks(product,{},remote,{})
        self.assertEqual(len(remote.calls),1)
        self.assertEqual(product["accessories"][0]["bazaarCheck"]["lastSuccessful"],previous)
        self.assertEqual(product["accessories"][1]["bazaarCheck"]["status"],"source_error")

    def test_full_identity_and_variants(self):
        remote=Source([row("123456789","Radio EU868"),row("123456788","Radio US915")])
        result=check_accessory("Radio EU868",remote)
        self.assertEqual(result["status"],"confirmed")
        self.assertEqual(result["match"]["sku"],"123456789")
        result=check_accessory("Radio",Source(remote.items))
        self.assertEqual(result["status"],"candidates")
        self.assertNotIn("match",result)

    def test_exact_sku_and_link_guard(self):
        remote=Source([row("123456789","Module")])
        self.assertEqual(check_accessory("Module",remote,"123456789")["status"],"confirmed")
        result=check_accessory("Module",remote,"123456789","https://www.seeedstudio.com/other.html")
        self.assertEqual(result["status"],"candidates")
        self.assertEqual(check_accessory("Module",Source(),"123456789")["status"],"not_found")

    def test_unrelated_results_and_no_url(self):
        result=check_accessory("SIM8202G-M2 5G module",Source([row("123456789","SenseCAP M2 gateway")]))
        self.assertEqual(result["candidates"],[])
        self.assertEqual(result["status"],"no_title_match")
        self.assertEqual(check_accessory("Module",Source([row("123456789","Module","")]))["status"],"no_title_match")

    def test_errors_and_retry_boundary(self):
        report=check_accessory("Module",Source(error=RateLimit(2000000000)))
        self.assertEqual(report["status"],"rate_limited")
        self.assertEqual(report["retryAfter"],2000000000)
        report=check_accessory("Module",Source(error=Problem("ROBOTS_EXCLUDED")))
        self.assertEqual(report["status"],"excluded")
        report=check_accessory("Module",Source(error=Problem("STORE_HTTP_403")))
        self.assertEqual(report["status"],"source_error")

    def test_same_published_sku_is_queried_once(self):
        remote=Source([row("123456789","Radio module")])
        cache={}
        check_accessory("Radio",remote,"123456789",cache=cache)
        check_accessory("Radio module",remote,"123456789",cache=cache)
        self.assertEqual(len(remote.calls),1)
        check_accessory("Radio",remote,"123456789")
        self.assertEqual(len(remote.calls),2)
        self.assertEqual(search_term("BL-M8723DU1 Wi-Fi/Bluetooth module"),"bl-m8723du1")
        self.assertEqual(search_term("WM1303 LoRaWAN gateway module (SPI, EU868)"),"wm1303")


if __name__=="__main__":unittest.main()
