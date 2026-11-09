import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from .catalog_images import reconcile_images
from .catalog_release import install_prepared,inventory_digest,merge_wiki_buttons
from .storage import CATALOG_PREFIX,packed


class CatalogueReleaseTests(unittest.TestCase):
    def test_installs_a_completed_snapshot_only_against_its_original_public_catalogue(self):
        with TemporaryDirectory() as tmp:
            root,stage=Path(tmp)/"workbench",Path(tmp)/"review"
            (root/"data").mkdir(parents=True)
            stage.mkdir()
            def snapshot(unread):
                return CATALOG_PREFIX.encode()+packed({"products":[{"sku":"abc"}],"audit":{"detail":{"unread":unread,"all":1},"documents":{"uniqueLinked":1}}})+b";\n"
            original=CATALOG_PREFIX.encode()+packed({"products":[{"sku":"abc"}]})+b";\n"
            installed=root/"data/catalog.js"
            reviewed=stage/"final.js"
            installed.write_bytes(original)
            (stage/"run.json").write_bytes(packed({"baseDigest":hashlib.sha256(original).hexdigest()}))
            reviewed.write_bytes(snapshot(1))
            with self.assertRaisesRegex(ValueError,"completed catalogue"):install_prepared(stage,reviewed,root)
            self.assertEqual(installed.read_bytes(),original)
            reviewed.write_bytes(snapshot(0))
            result=install_prepared(stage,reviewed,root)
            self.assertEqual(result["products"],1)
            self.assertEqual(installed.read_bytes(),reviewed.read_bytes())
            with self.assertRaisesRegex(ValueError,"changed since"):install_prepared(stage,reviewed,root)
            self.assertFalse((root/".local-workbench").exists())

    def test_preserves_image_only_for_the_same_official_source(self):
        with TemporaryDirectory() as tmp:
            base=Path(tmp)/"public"
            stage=Path(tmp)/"stage"
            blob=BytesIO()
            Image.new("RGB",(5,5),"white").save(blob,format="JPEG")
            raw=blob.getvalue()
            file="data/jpg/"+hashlib.sha256(raw).hexdigest()+".jpg"
            (base/file).parent.mkdir(parents=True)
            (base/file).write_bytes(raw)
            source="https://media-cdn.seeedstudio.com/media/catalog/product/a.jpg"
            old={"products":[{"sku":"a","image":file,"imageUrl":source}]}
            new={"products":[{"sku":"a","imageUrl":source},{"sku":"b","imageUrl":source},{"sku":"c","imageUrl":""}]}
            with patch("backend.catalog_images.PhotoStore.fetch_photo",side_effect=AssertionError("unexpected remote request")):
                result=reconcile_images(old,new,base,stage)
            self.assertEqual((result["verifiedSkus"],result["verifiedFiles"],result["missingSourceSkus"]),(2,1,1))
            self.assertEqual(new["products"][1]["image"],file)
            self.assertEqual(new["products"][2]["image"],"")

    def test_preview_hash_excludes_enrichment_and_respects_real_changes(self):
        base={"products":[{"sku":"123","groups":["b","a"],"price":4,"notes":[]}]}
        enriched={"products":[{"sku":"123","groups":["a","b"],"price":4,"notes":["evidence"],"detailAudit":{}}]}
        self.assertEqual(inventory_digest(base),inventory_digest(enriched))
        enriched["products"][0]["price"]=8
        self.assertNotEqual(inventory_digest(base),inventory_digest(enriched))

    def test_wiki_purchase_provenance_does_not_replace_verified_facts(self):
        url="https://wiki.seeedstudio.com/foo/"
        catalog={"audit":{},"products":[{"sku":"abc","wikiEvidence":[{"url":url+"#manual"}]}]}
        evidence={"products":[{"sku":"abc","wikiLinks":[{"url":url,"relation":"purchase_link"},{"url":url+"bar/","relation":"purchase_link"}]}]}
        merge_wiki_buttons(catalog,evidence)
        merge_wiki_buttons(catalog,evidence)
        self.assertEqual(len(catalog["products"][0]["wikiLinks"]),1)
        self.assertEqual(catalog["products"][0]["wikiEvidence"][0]["url"],url+"#manual")
