import json

import pytest

from izanagi.base import build_snapshot, write_snapshot
from izanagi.delta import build_delta, write_delta


@pytest.fixture
def setup_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    output = project / ".izanagi"
    output.mkdir()

    config = {
        "project": {"name": "test-project", "output_dir": ".izanagi"},
        "scan": {
            "include_hidden_files": True,
            "inclusions": {"rules": ["*.py", "*.md"]},
            "exclusions": {"rules": ["private.py"]},
        },
        "preamble": {
            "base_preamble": "Base snapshot",
            "incremental_preamble": (
                "Delta relative to base {base_snapshot_id}"
            ),
        },
    }

    return project, output, config


def create_base(project, output, config):
    snapshot = build_snapshot(project, config=config)
    write_snapshot(snapshot, output)
    archive = output / "bases" / snapshot["manifest"]["snapshot_id"]
    write_snapshot(snapshot, archive)
    return snapshot["manifest"]["snapshot_id"]


def test_delta_reports_added_modified_deleted_and_unchanged(setup_project):
    project, output, config = setup_project

    (project / "unchanged.py").write_text("keep\n")
    (project / "modified.py").write_text("old version\n")
    (project / "deleted.py").write_text("remove me\n")
    base_id = create_base(project, output, config)

    (project / "modified.py").write_text("new version\n")
    (project / "deleted.py").unlink()
    (project / "added.py").write_text("new file\n")

    delta = build_delta(
        project, config=config, output_root=output, base_id=base_id
    )
    changes = {
        (change["path"], change["action"])
        for change in delta["manifest"]["changes"]
    }

    assert changes == {
        ("added.py", "added"),
        ("modified.py", "modified"),
        ("deleted.py", "deleted"),
    }
    assert "new file\n" in delta["delta"]
    assert "new version\n" in delta["delta"]
    assert "remove me\n" not in delta["delta"]
    assert delta["manifest"]["summary"]["unchanged_count"] >= 1


def test_delta_defaults_to_latest_base(setup_project):
    project, output, config = setup_project
    (project / "main.py").write_text("version one\n")
    first_id = create_base(project, output, config)

    (project / "main.py").write_text("version two\n")
    second_id = create_base(project, output, config)

    (project / "main.py").write_text("version three\n")
    delta = build_delta(project, config=config, output_root=output)

    assert second_id != first_id
    assert delta["manifest"]["base_snapshot_id"] == second_id
    assert "version three\n" in delta["delta"]


def test_delta_rejects_unknown_base(setup_project):
    project, output, config = setup_project

    with pytest.raises(ValueError, match="was not found"):
        build_delta(
            project,
            config=config,
            output_root=output,
            base_id="missing-base-id",
        )


def test_delta_manifest_is_written(setup_project):
    project, output, config = setup_project
    (project / "main.py").write_text("one\n")
    create_base(project, output, config)

    (project / "main.py").write_text("two\n")
    delta = build_delta(project, config=config, output_root=output)
    delta_path, manifest_path = write_delta(delta, output / "deltas")

    assert delta_path.is_file()
    assert manifest_path.is_file()
    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved["base_snapshot_id"] == delta["manifest"]["base_snapshot_id"]


def test_delta_aborts_on_unreadable_file_record(setup_project, monkeypatch):
    import izanagi.delta as delta_module

    project, output, config = setup_project
    (project / "main.py").write_text("base\n")
    create_base(project, output, config)

    original = delta_module.manifest_project

    def incomplete_scan(*args, **kwargs):
        result = original(*args, **kwargs)
        result["files"].append(
            {
                "path": "broken.py",
                "kind": "unreadable",
                "included": False,
                "reason": "file read error",
                "size_bytes": None,
            }
        )
        return result

    monkeypatch.setattr(delta_module, "manifest_project", incomplete_scan)

    with pytest.raises(ValueError, match="scan was incomplete"):
        build_delta(project, config=config, output_root=output)