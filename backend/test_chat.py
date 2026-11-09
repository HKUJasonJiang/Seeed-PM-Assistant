"""Offline/local-only conversation checks. No provider connections or production writes."""
from contextlib import closing
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import ProxyHandler,Request,build_opener

from .chat_context import prepare_turn
from .chats import Chats
from .server import create
from .storage import CATALOG_PREFIX, ROOT, Problem, Store, packed,write
from .test_service import product


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        snapshot=json.loads((ROOT/"data/catalog.js").read_text("utf8")[len(CATALOG_PREFIX):].strip().rstrip(";"))
        r1014=next((p for p in snapshot["products"] if p["sku"]=="100025879"),None)
        self.assertIsNotNone(r1014)
        self.records=[product("B-200"),product("A-100"),r1014]
        write(self.root/"data/catalog.js",CATALOG_PREFIX.encode()+packed({"products":self.records,"stats":{"total":3},"categories":[],"docs":snapshot["docs"]})+b";\n")
        self.store=Store(self.root/"private",self.root)
        self.seen=[]
        self.chat=Chats(self.store,threading.Lock(),self.fake)
        self.ident=self.chat.create({"lang":"en"})["chat"]["id"]

    def fake(self,provider,key,packet):
        request=json.loads(packet["messages"][-1]["content"])
        self.seen.append(request)
        sources=request["sources"]
        if not sources:return '{"points":[{"kind":"question","text":"Which product should I check?","refs":[]}]}'
        return json.dumps({"points":[{"kind":"fact","text":"A verified result","refs":[sources[0]["id"]]}]})

    def authenticate(self):
        self.store.api_key=lambda provider:"sensitive-test-secret-value"

    def send(self,ident,query,sku="",context=None):
        return self.chat.send(self.ident,{"requestId":ident,"query":query,"sku":sku,"context":context or {"view":"assistant"}})["chat"]

    def test_multiturn_idempotency_failure_and_recovery(self):
        with self.assertRaisesRegex(Problem,"API_KEY_REQUIRED"):self.send("request-0001","Price?","A-100")
        self.assertEqual(self.seen,[])
        self.authenticate()
        first=self.send("request-0001","Price?","A-100")
        self.assertEqual(first,self.send("request-0001","Price?","A-100"))
        self.assertEqual(len(self.seen),1)
        self.assertEqual(first["turns"][0]["sources"][0]["sku"],"A-100")
        with self.assertRaisesRegex(Problem,"CHAT_REQUEST_CONFLICT"):self.send("request-0001","Different","A-100")
        self.chat.completion=lambda *args:'{"points":[{"text":"Unsupported","refs":[888]}]}'
        with self.assertRaisesRegex(Problem,"AI_CITATIONS_UNVERIFIED"):
            self.send("request-0002","Compare with the previous product","B-200")
        self.assertEqual(len(self.chat.read(self.ident)["chat"]["turns"]),1)
        self.chat.completion=self.fake
        self.send("request-0002","Compare with the previous product","B-200")
        self.assertEqual(self.seen[-1]["activeSKU"],"B-200")
        self.assertEqual(self.seen[-1]["previousComparisonSKUs"],["A-100"])
        self.assertEqual(self.seen[-1]["history"][0]["SKU"],"A-100")
        self.assertTrue({"A-100","B-200"}.issubset({s["sku"] for s in self.seen[-1]["sources"]}))
        before=self.chat.read(self.ident)
        self.chat=Chats(self.store,threading.Lock(),self.fake)
        self.assertEqual(before,self.chat.read(self.ident))
        self.assertNotIn("turns",self.chat.list()["chats"][0])
        self.assertNotIn("Compare",str(self.store.public()))

    def test_explicit_page_handling_and_local_records(self):
        self.authenticate()
        self.store.apply("product",{"sku":"A-100","custom":"可定制 WIFI、4G 模组","customConfirmed":True})
        st=self.store.apply("project",{"title":"Selected saved project","description":"CURRENT saved description","skus":["A-100"],"labels":["pilot"]})
        ident=st["projects"][0]["id"]
        self.store.apply("project",{"title":"Other customer project","description":"OTHER private description","skus":["A-100"]})
        self.send("request-1001","What can be customized?","A-100")
        packet=self.seen[-1]
        self.assertTrue(any(s["kind"]=="local" and s["sku"]=="A-100" and "4G" in str(s["facts"]) for s in packet["sources"]))
        self.assertFalse(any(s["kind"]=="official" and "4G" in str(s["facts"]) for s in packet["sources"] if s["sku"]=="A-100"))
        self.send("request-1002","Summarize the project",context={"view":"custom","tab":"project","projectId":ident,
                  "projectDraft":{"title":"Fresh unsaved draft","description":"DRAFT changed quantity to 50","skus":["A-100"],"customerPhone":"private-number"}})
        self.assertIn("DRAFT changed quantity to 50",str(self.seen[-1]))
        self.assertIn("CURRENT saved description",str(self.seen[-1]))
        self.assertNotIn("OTHER private description",str(self.seen[-1]))
        self.assertNotIn("private-number",str(self.seen[-1]))
        self.send("request-1003","What can I do here?",context={"view":"developer","tab":"settings","sku":"B-200","query":"FORM PASSWORD","apiKey":"test-value","selectedSkus":["A-100"]})
        p=self.seen[-1]
        self.assertEqual(p["currentPage"],{"view":"developer","tab":"settings"})
        self.assertEqual(p["activeSKU"],"")
        self.assertFalse(any(s["sku"] for s in p["sources"]))
        self.assertEqual({s["kind"] for s in p["sources"]},{"context"})
        self.assertNotIn("FORM PASSWORD",str(p))
        self.send("request-1004","List items on this page",context={"view":"catalog","page":1,"visibleSkus":["B-200"],"total":1,"apiKey":"test-value"})
        packet=self.seen[-1]
        self.assertEqual(packet["activeSKU"],"")
        self.assertEqual({s["sku"] for s in packet["sources"] if s["sku"]},{"B-200"})
        self.assertNotIn("test-value",str(packet))
        self.send("request-1005","Review sensitive-test-secret-value please",context={"view":"coverage"})
        self.assertNotIn("sensitive-test-secret-value",str(self.seen[-1]))
        self.assertNotIn("sensitive-test-secret-value",str(self.chat.read(self.ident)))
        self.assertIn("catalogCounts",str(self.seen[-1]))

    def test_real_filtered_accessories(self):
        self.authenticate()
        self.send("request-2001","这两款有什么区别？","100025879",{"view":"assistant","tab":"accessories","filter":"EU868"})
        packet=self.seen[-1]
        evidence=[(f,s["url"]) for s in packet["sources"] if s["kind"]=="official" and s["sku"]=="100025879" for f in s["facts"]]
        for sku,interface in (("114993268","SPI"),("114992628","USB")):
            self.assertTrue(any(sku in f and "EU868" in f and interface in f and url.startswith("https://wiki.seeedstudio.com/") for f,url in evidence))

    def test_concurrent_duplicate(self):
        self.authenticate()
        started=threading.Event();finish=threading.Event()
        def slow(*args):
            started.set();finish.wait(3)
            return self.fake(*args)
        self.chat.completion=slow
        t=threading.Thread(target=self.send,args=("request-3001","Question","A-100"))
        t.start()
        try:
            self.assertTrue(started.wait(2))
            with self.assertRaisesRegex(Problem,"AI_REQUEST_RUNNING"):self.send("request-3001","Question","A-100")
        finally:finish.set();t.join(3)
        self.send("request-3001","Question","A-100")
        self.assertEqual(len(self.seen),1)

    def test_http_boundaries(self):
        server=create(0,self.root/"web-test-user",self.root)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            origin="http://127.0.0.1:"+str(server.server_address[1])
            http=build_opener(ProxyHandler({}))
            def request(path,body=None,headers=None):
                req=Request(origin+path,data=packed(body) if body is not None else None,headers=headers or {})
                with http.open(req) as r:return json.load(r)
            state=request("/api/state")
            headers={"Origin":origin,"X-CSRF-Token":state["csrf"],"Content-Type":"application/json"}
            with self.assertRaises(HTTPError) as denied:request("/api/chats",{},{"Origin":origin,"Content-Type":"application/json"})
            self.assertEqual(denied.exception.code,403)
            ident=request("/api/chats",{"title":"Local-only title"},headers)["chat"]["id"]
            self.assertEqual(request("/api/chats/"+ident)["chat"]["turns"],[])
            with self.assertRaises(HTTPError) as denied:request("/api/chats",headers={"Origin":"https://example.com"})
            self.assertEqual(denied.exception.code,403)
            with self.assertRaises(HTTPError) as denied:request("/.local-workbench/chats.sqlite3")
            self.assertEqual(denied.exception.code,404)
            self.assertNotIn("Local-only title",str(request("/api/state")))
            self.assertEqual(request("/api/chats/"+ident+"/delete",{},headers),{"ok":True})
        finally:
            server.shutdown();server.server_close();server.instance.close();thread.join(3)


if __name__=="__main__":unittest.main()
