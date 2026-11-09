"""The maintainer CLI reads exact public files and verifies transferred bytes."""
import base64
import hashlib
import json
import unittest
from unittest.mock import patch
from .document_github import PublicGitHubCLI
from .document_enrichment import github_file


class PublicAttachmentTests(unittest.TestCase):
    target=github_file("https://github.com/SeeedDocument/Example/raw/master/Doc%20A.pdf")
    data=b"%PDF-1.4\n\x1a\x00\n%%EOF"

    def test_public_repository_gate_precedes_binary_transfer(self):
        client=PublicGitHubCLI()
        allow={"private":False,"visibility":"public","full_name":"SeeedDocument/Example","owner":{"login":"SeeedDocument"}}
        private={**allow,"private":True,"visibility":"private","full_name":"SeeedDocument/Other"}
        safety=[(200,{},b'{"resources":{"core":{"limit":5000,"remaining":4900}}}'),(200,{},json.dumps([allow,private]).encode())]
        with patch.object(client,"call",side_effect=safety) as api:
            client.prepare([self.target[0],self.target[0].replace("Example","Other")])
        self.assertEqual(api.call_args_list[1].args,("users/SeeedDocument/repos?type=owner&per_page=100&page=1",))
        with patch.object(client,"call",side_effect=AssertionError("A non-public repository must not be opened")):
            result,body=client.fetch(tuple(x.replace("Example","Other") for x in self.target))
        self.assertEqual(result["reason"],"public_repository_unconfirmed")
        self.assertIsNone(body)

    def test_inline_and_large_blob_use_same_repo_size_and_git_hash(self):
        client=PublicGitHubCLI();client.public={"seeeddocument/example":"SeeedDocument/Example"}
        length=len(self.data)
        digest=hashlib.sha1(b"blob "+str(length).encode()+b"\0"+self.data).hexdigest()
        original={"type":"file","path":"Doc A.pdf","size":length,"sha":digest,
                  "git_url":"https://api.github.com/repos/SeeedDocument/Example/git/blobs/"+digest,
                  "encoding":"base64","content":base64.b64encode(self.data).decode()}
        for large in (False,True):
            replies=[{**original,"content":"","encoding":"none"},original] if large else [original]
            with patch.object(client,"call",side_effect=[(200,{},json.dumps(v).encode()) for v in replies]) as api:
                meta,body=client.fetch(self.target)
            self.assertEqual((meta["gitBlobSha"],body),(digest,self.data))
            if large:self.assertEqual(api.call_args.args[0],"repos/SeeedDocument/Example/git/blobs/"+digest)
        for field,value in (("path","Other.pdf"),("size",length+1),("sha","0"*40),("content","A==="),
                            ("git_url","https://api.github.com/repos/elsewhere/Example/git/blobs/"+digest)):
            with patch.object(client,"call",return_value=(200,{},json.dumps({**original,field:value}).encode())):
                meta,body=client.fetch(self.target)
            self.assertEqual(meta["status"],"unread")
            self.assertIsNone(body)

    def test_forbidden_resource_does_not_fall_back_to_another_host(self):
        client=PublicGitHubCLI();client.public={"seeeddocument/example":"SeeedDocument/Example"}
        with patch.object(client,"call",return_value=(403,{},b"denied")) as api:
            meta,body=client.fetch(self.target)
        self.assertEqual(api.call_count,1)
        self.assertEqual(meta["reason"],"http_403")
        self.assertIsNone(body)
