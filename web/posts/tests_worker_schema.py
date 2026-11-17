"""The worker reads posts_post with plain SQL (worker/db.py).

If a migration renames or drops one of those columns, the worker would
only break at run time; this test catches it in the web test suite.
It is skipped inside the web Docker image, which has no worker code.
"""

import ast
import unittest
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .models import Post

WORKER_DB = Path(settings.BASE_DIR).parent / "worker" / "db.py"


def worker_constant(name):
    tree = ast.parse(WORKER_DB.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets[0].id == name:
            return ast.literal_eval(node.value)
    raise LookupError(name)


@unittest.skipUnless(WORKER_DB.exists(), "worker code not available")
class WorkerSchemaTests(SimpleTestCase):
    def test_table_name(self):
        self.assertEqual(worker_constant("TABLE"), Post._meta.db_table)

    def test_worker_columns_exist(self):
        columns = {field.column for field in Post._meta.concrete_fields}
        missing = set(worker_constant("POST_COLUMNS")) - columns
        self.assertFalse(missing, f"worker/db.py uses unknown columns: {missing}")

    def test_status_values_match(self):
        for name in ("SCHEDULED", "PUBLISHING", "PUBLISHED", "FAILED"):
            self.assertIn(worker_constant(name), Post.Status.values)
