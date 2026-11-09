import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from .preview_migration import publish,recover_preview
from .storage import CATALOG_PREFIX, packed


def catalog_bytes(item):
    return CATALOG_PREFIX.encode()+packed({"products":[item]})+b";\n"


class PreviewMigrationTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.local=Path(temp.name)
        self.file=self.local/"catalog.js"
        self.item={"sku":"17","name":"Gateway","price":20}
        self.original=catalog_bytes(self.item)
        self.new=catalog_bytes({**self.item,"attributes":[{"name":"Storage","value":"16GB"}]})
        self.baseline=hashlib.sha256(self.original).hexdigest()
        self.file.write_bytes(self.original)
        (self.local/"update-state.json").write_text('{"action":"preview","status":"ready"}')
        db=sqlite3.connect(self.local/"update-work.sqlite")
        self.addCleanup(db.close)
        self.db=db
        with db:
            db.execute("CREATE TABLE kv(k TEXT PRIMARY KEY,v TEXT)")
            db.execute("INSERT INTO kv VALUES ('baseDigest',?)",(json.dumps(self.baseline),))
            db.execute("CREATE TABLE pending(sku TEXT PRIMARY KEY,done INT)")
            db.execute("INSERT INTO pending VALUES ('17',0)")

    def test_preserves_existing_preview(self):
        publish(self.file,self.local,self.new,self.baseline)
        baseline=self.db.execute("SELECT v FROM kv WHERE k='baseDigest'").fetchone()[0]
        self.assertEqual(json.loads(baseline),hashlib.sha256(self.new).hexdigest())
        self.assertEqual(self.db.execute("SELECT * FROM pending").fetchall(),[("17",0)])
        self.assertFalse(self.db.execute("SELECT * FROM kv WHERE k='detailRelease'").fetchall())

    def test_different_price_rejected(self):
        with self.assertRaises(ValueError):
            publish(self.file,self.local,catalog_bytes({**self.item,"price":21}),self.baseline)
        self.assertEqual(self.file.read_bytes(),self.original)

    def test_prepared_checkpoint_recovers_after_atomic_file_replacement(self):
        with patch("backend.preview_migration.recover_preview",side_effect=[None,RuntimeError("interrupted")]):
            with self.assertRaises(RuntimeError):
                publish(self.file,self.local,self.new,self.baseline)
        recover_preview(self.file,self.local)
        self.assertEqual(self.file.read_bytes(),self.new)
        baseline=self.db.execute("SELECT v FROM kv WHERE k='baseDigest'").fetchone()[0]
        self.assertEqual(json.loads(baseline),hashlib.sha256(self.new).hexdigest())
