import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from izanagi.base import build_snapshot, write_snapshot


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()
        self.config = {
            "project": {"name": "test-project"},
            "scan": {
                "include_hidden_files": True,
                "inclusions": {"rules": ["*.py", "*.md"]},
                "exclusions": {"rules": ["private.py"]},
            },
            "preamble": {"base_preamble": "Test snapshot preamble"},
        }

    def test_snapshot_preserves_included_content(self):
        content = "def hello():\n    return 'world'\n"
        (self.root / "main.py").write_text(content, encoding="utf-8")

        snapshot = build_snapshot(self.root, config=self.config)

        self.assertIn(content, snapshot["snapshot"])
        record = next(
            item for item in snapshot["manifest"]["files"] if item["path"] == "main.py"
        )
        self.assertEqual(record["sha256"], hashlib.sha256(content.encode()).hexdigest())

    def test_excluded_file_is_not_included_as_content(self):
        (self.root / "private.py").write_text("SECRET_MARKER")
        snapshot = build_snapshot(self.root, config=self.config)

        self.assertNotIn("SECRET_MARKER", snapshot["snapshot"])
        record = next(
            item
            for item in snapshot["manifest"]["files"]
            if item["path"] == "private.py"
        )
        self.assertFalse(record["included"])

    def test_snapshot_is_written_as_markdown_and_json(self):
        (self.root / "main.py").write_text("pass\n")
        snapshot = build_snapshot(self.root, config=self.config)
        output_dir = self.root / ".izanagi"

        snapshot_path, manifest_path = write_snapshot(snapshot, output_dir)

        self.assertTrue(snapshot_path.is_file())
        self.assertTrue(manifest_path.is_file())
        self.assertIn("## Directory Structure", snapshot_path.read_text())
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["snapshot_id"], snapshot["manifest"]["snapshot_id"])


if __name__ == "__main__":
    unittest.main()