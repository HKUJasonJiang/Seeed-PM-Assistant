"""Offline regression tests; every update and credential uses a temporary installation."""
import base64
import copy
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from .assistant import answer
from .server import create
from .storage import CATALOG_PREFIX, Problem, Store, customization_info, packed, write
from .storefront import RateLimit
from .updates import Updates

STORE="https://www.seeedstudio.com/"
WIKI="https://wiki.seeedstudio.com/example/"

def product(sku):
    return {"sku":sku,"name":"Hardware "+sku,"url":STORE+sku+".html","price":12,"maxPrice":12,"currency":"USD",
            "summary":"Official description","image":"","imageUrl":"","groups":["Group"],"paths":[],"docs":[],"notes":[],
            "parts":[],"details":False,"updated":"2026-11-08"}

class FakeStore:
    def __init__(self):
        self.interrupt=False
        self.touched=[]
        self.image_calls=0
        self.detail_error=False

    def categories(self):
        return [{"id":"2","name":"Group","url":STORE+"Group.html"}]

    def category_page(self,cat,page):return ["A100","NEW200"],2,1

    def listing(self,page,skus=None):
        items=[]
        for sku in ("A100","NEW200"):
            if skus is not None and sku not in skus:continue
            items.append({"sku":sku,"name":"Hardware "+sku,"url_key":sku,"url_suffix":".html",
                          "small_image":{"url":"https://media.seeedstudio.com/same.jpg"},
                          "categories":[],"price_range":{"minimum_price":{"final_price":{"value":14,"currency":"USD"}},
                          "maximum_price":{"final_price":{"value":14,"currency":"USD"}}},
                          "short_description":{"html":"<p>Official description</p>"},"description":{"html":"<p>Hardware</p>"}})
        return items,len(items),1

    def detail(self,url,sku):
        self.touched.append(sku)
        if self.interrupt and sku=="NEW200":
            self.interrupt=False
            raise RateLimit(time.time()-1)
        if self.detail_error:raise Problem("DETAIL_LAYOUT_UNKNOWN")
        return {"documents":'<a href="https://files.seeedstudio.com/new.pdf">New sheet</a>',
                "certification_info_part":"<table><tr><td>Device</td><td>1</td></tr></table>",
                "addons":[]}

    def main_image(self,url,root):
        self.image_calls+=1
        name="data/jpg/"+"a"*64+".jpg"
        write(root/name,b"fake isolated test image")
        return name

class CheckWorkbench(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.local=self.root/"user"
        p=product("A100")
        p.update(custom="Logo option",customUrl=WIKI,wikiEvidence=[{"url":WIKI,"title":"Hardware A100 guide","zh":"系列事实","en":"Series fact"}],
                 details=True,parts=[["Old","1"]],docs=[{"name":"Old sheet","url":STORE+"old.pdf"}],
                 notes=[{"kind":"另购说明","text":"Obsolete exclusion","source":p["url"]},
                        {"kind":"另购说明","text":"Independent manual","source":"https://files.seeedstudio.com/guide.pdf#page=7"}],
                 missingSummary=["Obsolete exclusion"],accessories=[{"sku":"OLD","type":"商品页 Also Add 加购项","name":"Old add-on"}])
        data={"categories":[{"name":"Group","url":STORE+"Group.html"}],"stats":{},"docs":{},"products":[p,product("MISSING")]}
        write(self.root/"data/catalog.js",CATALOG_PREFIX.encode()+packed(data)+b";\n")
        write(self.root/"index.html",b"<title>Isolated test workbench</title>")
        self.store=Store(self.local,self.root)
        self.remote=FakeStore()

    def run_job(self,updates,**request):
        updates.start(request)
        updates.thread.join(timeout=10)
        self.assertFalse(updates.thread.is_alive())
        return updates.status()

    def test_preview_resume_full_and_selective(self):
        u=Updates(self.store,self.remote)
        self.store.apply("product",{"sku":"A100","name":"Private name"})
        before=(self.root/"data/catalog.js").read_bytes()
        preview=self.run_job(u,action="preview")
        self.assertEqual(preview["status"],"ready",preview)
        self.assertEqual(preview["lastAppliedAt"],"2026-11-08")
        self.assertIn("T",preview["lastCheckedAt"])
        self.assertEqual({x["kind"] for x in preview["changes"]},{"new","changed","missing"})
        self.assertEqual(before,(self.root/"data/catalog.js").read_bytes())
        self.remote.interrupt=True
        self.assertEqual(self.run_job(u,action="apply",categories=["Group"])["status"],"paused")
        self.assertEqual(before,(self.root/"data/catalog.js").read_bytes())
        resumed=Updates(self.store,self.remote)
        self.assertEqual(self.run_job(resumed,action="resume")["status"],"done")
        self.assertIn("T",resumed.status()["lastAppliedAt"])
        self.assertEqual(self.remote.touched.count("A100"),1)
        self.assertEqual(self.remote.image_calls,1)
        p=self.store.by_sku["a100"]
        self.assertEqual(p["docs"],[{"name":"New sheet","url":"https://files.seeedstudio.com/new.pdf"}])
        self.assertEqual(p["parts"],[["Device","1"]])
        self.assertNotIn("Obsolete exclusion",str(p["notes"])+str(p["missingSummary"]))
        self.assertEqual(p["accessories"],[])
        self.assertTrue(any(n["text"]=="Independent manual" for n in p["notes"]))
        self.assertEqual(p["wikiEvidence"][0]["url"],WIKI)
        self.assertEqual(self.store.effective("A100")["name"],"Private name")
        self.assertIn("missing",self.store.by_sku)
        self.remote.detail_error=True
        result=self.run_job(resumed,action="refresh",skus=["A100"])
        self.assertEqual(result["status"],"done",result)
        self.assertEqual(result["warningCount"],1)
        self.assertEqual(self.remote.image_calls,2) # Same external image URL was read on forced refresh.
        self.assertEqual(self.store.by_sku["a100"]["docs"],p["docs"])
        self.remote.detail_error=False
        self.assertEqual(self.run_job(resumed,action="refresh")["status"],"done")
        self.assertFalse(resumed.dbfile.exists())
        self.assertFalse((self.root/".cache").exists())

    @unittest.skipUnless(os.name=="nt","Windows account credential vault")
    def test_vault_citations_overrides(self):
        secret=secrets.token_hex(22)
        state=self.store.apply("settings",{"apiKey":secret})
        self.assertTrue(state["providers"]["deepseek"]["hasKey"])
        self.assertNotIn(secret,json.dumps(state))
        self.assertNotIn(secret,self.store.state_file.read_text("utf8"))
        self.store.apply("product",{"sku":"A100","summary":"Unpublished confidential notes"})
        fresh=Store(self.local,self.root)
        def fake(provider,key,payload):
            self.assertEqual(secret,key)
            self.assertNotIn("confidential",str(payload))
            self.assertIn("Series fact",str(payload))
            return '{"points":[{"text":"Cited result","refs":[1]}]}'
        a=answer(fresh,{"sku":"A100","query":"What is supported?","lang":"en"},fake)
        self.assertEqual(a["sources"][0]["url"],WIKI)
        with self.assertRaisesRegex(Problem,"AI_CITATIONS_UNVERIFIED"):
            answer(fresh,{"sku":"A100","query":"?"},lambda *args:'{"points":[{"text":"test","refs":[999]}]}')
        state=fresh.apply("settings",{"provider":"doubao","model":"example-model","apiKey":secret+"2"})
        self.assertTrue(state["providers"]["deepseek"]["hasKey"])
        state=fresh.apply("settings",{"provider":"deepseek","clearKey":True})
        self.assertFalse(state["providers"]["deepseek"]["hasKey"])
        self.assertTrue(state["providers"]["doubao"]["hasKey"])

    def test_work_and_images(self):
        from PIL import Image
        import base64
        out=io.BytesIO(); Image.new("RGB",(8,4),"white").save(out,"JPEG")
        image="data:image/jpeg;base64,"+base64.b64encode(out.getvalue()).decode()
        self.store.apply("product",{"sku":"PM-100","name":"Manual","create":True,"customConfirmed":True,"image":image})
        self.store.apply("favorite",{"sku":"PM-100","active":True})
        self.store.apply("project",{"title":"Custom","skus":["PM-100","A100"],"labels":["用户标签"]})
        state=Store(self.local,self.root).public()
        self.assertEqual(state["favorites"],["PM-100"])
        self.assertEqual(state["projects"][0]["skus"],["PM-100","A100"])
        self.assertTrue((self.local/state["overrides"]["PM-100"]["image"][1:]).is_file())
        self.store.apply("product",{"sku":"PM-100","image":""})
        self.assertEqual(list((self.local/"user-images").glob("*.jpg")),[])
        with self.assertRaisesRegex(Problem,"CUSTOMIZATION_UNCONFIRMED"):
            self.store.apply("project",{"title":"x","skus":["MISSING"]})
        p=product("NEW300")
        p["notes"]=[{"kind":"定制说明","source":p["url"],"text":"We offer logo customization services for Hardware NEW300, including custom printing."}]
        self.assertIsNotNone(customization_info(p))
        p["notes"][0]["text"]="We offer logo customization services for Other Board, including custom printing."
        self.assertIsNone(customization_info(p))

    def test_http_isolation(self):
        server=create(0,self.local,self.root)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        origin=f"http://127.0.0.1:{server.server_address[1]}"
        net=build_opener(ProxyHandler({}))
        try:
            snapshot=json.load(net.open(origin+"/api/state"))
            navigation={"Sec-Fetch-Mode":"navigate","Sec-Fetch-Dest":"document","Sec-Fetch-Site":"cross-site"}
            self.assertIn(b"Isolated test",net.open(Request(origin+"/",headers=navigation)).read())
            with self.assertRaises(HTTPError) as err:net.open(Request(origin+"/api/state",headers=navigation))
            self.assertEqual(err.exception.code,403)
            for path in ("/user/workbench.json","/.local-workbench/workbench.json","/backend/server.py","/data/manuals/r11.pdf"):
                with self.assertRaises(HTTPError) as err:net.open(origin+path)
                self.assertEqual(err.exception.code,404)
            def post(path,body,headers):
                return json.load(net.open(Request(origin+path,data=packed(body),headers={"Content-Type":"application/json",**headers})))
            with self.assertRaises(HTTPError) as err:post("/api/settings",{"language":"en"},{})
            self.assertEqual(err.exception.code,403)
            good={"Origin":origin,"X-CSRF-Token":snapshot["csrf"]}
            self.assertEqual(post("/api/settings",{"language":"en"},good)["language"],"en")
            with self.assertRaises(HTTPError) as err:post("/api/ai",{"sku":"A100","query":"hello","lang":"en"},good)
            self.assertEqual(json.load(err.exception)["error"],"API_KEY_REQUIRED")
        finally:
            server.shutdown();thread.join(2);server.server_close();server.instance.close()


if __name__=="__main__":unittest.main()
