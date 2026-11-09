"""Browser/HTTP/model integration check with an isolated profile and an in-process provider."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading

from backend.server import create
from backend.storage import ROOT


def main():
    calls=[]
    def fake_completion(provider,key,request):
        context=json.loads(request["messages"][1]["content"])
        calls.append(context)
        sources=context["sources"]
        preferred=next((s for s in sources if s["kind"]=="local" and s.get("sku")=="114110314"),None)
        ref=preferred or sources[0]
        return json.dumps({"points":[{"text":"Fixture reply "+str(len(calls)),"refs":[ref["id"]]}]})

    with tempfile.TemporaryDirectory() as directory:
        server=create(0,Path(directory))
        server.chats.completion=fake_completion
        server.store.apply("settings",{"language":"en","apiKey":secrets.token_urlsafe(36)})
        server.store.apply("product",{"sku":"114110314","customConfirmed":True,"custom":"Fixture manual Wi-Fi / 4G service"})
        server.store.apply("favorite",{"sku":"114110314","active":True})
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            address="http://127.0.0.1:"+str(server.server_address[1])
            subprocess.run(["node","tools/verify_chat.cjs"],cwd=ROOT,check=True,
                           env={**os.environ,"SEEED_CHAT_FIXTURE":address})
            assert len(calls)==5
            product,comparison,listing,project,settings=calls
            assert product["activeSKU"]=="114110314" and not product["history"]
            assert any("Fixture manual Wi-Fi / 4G service" in str(s["facts"]) and s["kind"]=="local" for s in product["sources"])
            assert comparison["activeSKU"]=="100025879" and comparison["currentPage"]["tab"]=="accessories"
            assert comparison["currentPage"]["filter"]=="EU868" and "114110314" in comparison["previousComparisonSKUs"]
            assert comparison["history"][-1]["SKU"]=="114110314"
            assert listing["activeSKU"]=="" and listing["currentPage"]["view"]=="catalog" and listing["currentPage"]["query"]=="XIAO"
            assert listing["currentPage"]["visibleSkus"] and not listing["history"]
            assert project["currentPage"]["projectDraft"]["description"]=="Fixture draft only: wall mounting"
            assert project["currentPage"]["projectDraft"]["skus"]==["114110314"]
            assert settings["currentPage"]=={"view":"developer","tab":"settings"}
            assert "unsaved-secret-fixture" not in json.dumps(calls)
            print("Five user-initiated mock calls verified. No external model requests.")
        finally:
            server.shutdown();thread.join();server.server_close();server.instance.close()


if __name__=="__main__":
    main()
