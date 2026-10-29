import tempfile
import unittest
from pathlib import Path

from izanagi.config import load_default_config
from izanagi.manifest import (
    classify_file,
    discover_git_root,
    inclusion_decision,
    manifest_project,
)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()
        self.config = {
            "scan": {
                "include_hidden_files": True,
                "inclusions": {"rules": ["*.py", "*.md", ".gitignore", "experiments/"]},
                "exclusions": {"rules": ["private.py", "blocked/"]},
            }
        }

    def test_classification_does_not_control_inclusion(self):
        self.assertEqual(classify_file(Path("image.png")), "binary_or_artifact")
        included, _ = inclusion_decision(
            Path("image.png"),
            inclusion_rules=["image.png"],
            exclusion_rules=[],
        )
        self.assertTrue(included)

    def test_file_patterns_match_at_any_depth(self):
        included, reason = inclusion_decision(
            Path("nested/model.py"),
            inclusion_rules=["*.py"],
            exclusion_rules=[],
        )
        self.assertTrue(included)
        self.assertIn("*.py", reason)

    def test_exclusions_win(self):
        included, reason = inclusion_decision(
            Path("private.py"),
            inclusion_rules=["*.py"],
            exclusion_rules=["private.py"],
        )
        self.assertFalse(included)
        self.assertIn("excluded", reason)

    def test_directory_inclusion_is_recursive(self):
        included, _ = inclusion_decision(
            Path("experiments/data.bin"),
            inclusion_rules=["experiments/"],
            exclusion_rules=[],
        )
        self.assertTrue(included)

    def test_root_anchored_file_pattern(self):
        rules = ["/special_config.json"]
        self.assertTrue(
            inclusion_decision(
                Path("special_config.json"),
                inclusion_rules=rules,
                exclusion_rules=[],
            )[0]
        )
        self.assertFalse(
            inclusion_decision(
                Path("nested/special_config.json"),
                inclusion_rules=rules,
                exclusion_rules=[],
            )[0]
        )

    def test_manifest_uses_configured_rules(self):
        (self.root / ".gitignore").write_text("*.tmp\n")
        (self.root / "main.py").write_text("pass\n")
        (self.root / "unknown.bin").write_bytes(b"123")
        result = manifest_project(self.root, config=self.config)
        records = {r["path"]: r for r in result["files"]}
        self.assertTrue(records[".gitignore"]["included"])
        self.assertTrue(records["main.py"]["included"])
        self.assertFalse(records["unknown.bin"]["included"])

    def test_excluded_directory_is_not_traversed(self):
        blocked = self.root / "blocked"
        blocked.mkdir()
        (blocked / "main.py").write_text("pass\n")
        result = manifest_project(self.root, config=self.config)
        paths = {r["path"] for r in result["files"]}
        self.assertNotIn("blocked/main.py", paths)
        self.assertIn("blocked/", paths)

    def test_directory_symlink_is_not_followed(self):
        target = self.root / "target"
        target.mkdir()
        (target / "main.py").write_text("pass\n")
        link = self.root / "linked"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks are not supported")
        result = manifest_project(self.root, config=self.config)
        records = {r["path"]: r for r in result["files"]}
        self.assertEqual(records["linked"]["kind"], "symlink")
        self.assertFalse(records["linked"]["included"])

    def test_manifest_is_sorted_and_summary_matches(self):
        for name in ("z.py", "a.py", "note.md"):
            (self.root / name).write_text("x")
        result = manifest_project(self.root, config=self.config)
        records = result["files"]
        summary = result["summary"]
        self.assertEqual(
            [r["path"] for r in records], sorted(r["path"] for r in records)
        )
        self.assertEqual(summary["file_count"], len(records))
        self.assertEqual(summary["included_count"], sum(r["included"] for r in records))
        self.assertEqual(
            summary["excluded_count"], sum(not r["included"] for r in records)
        )

    def test_git_root_can_be_an_ancestor(self):
        (self.root / ".git").mkdir()
        child = self.root / "nested"
        child.mkdir()
        self.assertEqual(discover_git_root(child), self.root)

    def test_bundled_config_includes_gitignore_rule(self):
        config = load_default_config()
        self.assertIn(".gitignore", config["scan"]["inclusions"]["rules"])


def test_specific_file_overrides_excluded_directory():
    included, reason = inclusion_decision(
        Path(".izanagi/config.toml"),
        inclusion_rules=["*.toml", ".izanagi/config.toml"],
        exclusion_rules=[".izanagi/"],
    )

    assert included is True
    assert "included" in reason


def test_other_files_in_excluded_directory_remain_excluded():
    included, reason = inclusion_decision(
        Path(".izanagi/other.toml"),
        inclusion_rules=["*.toml"],
        exclusion_rules=[".izanagi/"],
    )

    assert included is False
    assert "excluded" in reason


def test_excluded_directory_overrides_broad_file_pattern():
    for path in [".venv/example.py", ".git/config.py"]:
        included, _ = inclusion_decision(
            Path(path),
            inclusion_rules=["*.py"],
            exclusion_rules=[".venv/", ".git/"],
        )

        assert included is False, path


def test_exclusion_wins_equal_specificity_tie():
    included, _ = inclusion_decision(
        Path("src/example.py"),
        inclusion_rules=["src/example.py"],
        exclusion_rules=["src/example.py"],
    )

    assert included is False


def test_python_pattern_matches_files_at_any_depth():
    for path in ["main.py", "src/main.py", "src/nested/main.py"]:
        included, _ = inclusion_decision(
            Path(path),
            inclusion_rules=["*.py"],
            exclusion_rules=[],
        )

        assert included is True, path


def test_root_anchored_pattern_does_not_match_nested_file():
    included_root, _ = inclusion_decision(
        Path("special_config.json"),
        inclusion_rules=["/special_config.json"],
        exclusion_rules=[],
    )
    included_nested, _ = inclusion_decision(
        Path("config/special_config.json"),
        inclusion_rules=["/special_config.json"],
        exclusion_rules=[],
    )

    assert included_root is True
    assert included_nested is False


def test_manifest_includes_config_exception_under_excluded_directory(
    tmp_path,
):
    from izanagi.manifest import manifest_project

    izanagi_dir = tmp_path / ".izanagi"
    izanagi_dir.mkdir()

    config_file = izanagi_dir / "config.toml"
    config_file.write_text("[project]\nname = 'izanagi'\n")

    other_file = izanagi_dir / "other.toml"
    other_file.write_text("ignored = true\n")

    config = {
        "scan": {
            "include_hidden_files": True,
            "inclusions": {
                "rules": [
                    "*.toml",
                    ".izanagi/config.toml",
                ],
            },
            "exclusions": {
                "rules": [".izanagi/"],
            },
        },
    }

    result = manifest_project(tmp_path, config=config)
    files = {record["path"]: record for record in result["files"]}

    assert files[".izanagi/config.toml"]["included"] is True
    assert files[".izanagi/other.toml"]["included"] is False


if __name__ == "__main__":
    unittest.main()
