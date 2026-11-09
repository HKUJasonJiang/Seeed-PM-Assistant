"""Drive the same resumable update script as the developer UI, through the running local service."""
import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["status","preview","apply","refresh","resume"])
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--sku",action="append",default=[])
    parser.add_argument("--category",action="append",default=[])
    args=parser.parse_args()
    origin=f"http://127.0.0.1:{args.port}"
    client=build_opener(ProxyHandler({}))
    try:
        if args.action=="status":result=json.load(client.open(origin+"/api/update",timeout=10))
        else:
            token=json.load(client.open(origin+"/api/state",timeout=10))["csrf"]
            body=json.dumps({"action":args.action,"skus":args.sku,"categories":args.category}).encode()
            req=Request(origin+"/api/update", data=body,headers={"Content-Type":"application/json","Origin":origin,"X-CSRF-Token":token})
            result=json.load(client.open(req,timeout=15))
    except HTTPError as err:raise SystemExit(json.load(err).get("error","UPDATE_FAILED")) from None
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=="__main__":main()
