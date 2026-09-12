from hackathon_competitor.workspace import GitWorkspace


def test_git_workspace_checkpoints_and_reuses_clean_head(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "result.txt").write_text("first", encoding="utf-8")
    workspace = GitWorkspace(root)
    first = workspace.checkpoint("Initial result")
    assert len(first) == 40
    assert workspace.checkpoint("No changes") == first
    (root / "result.txt").write_text("second", encoding="utf-8")
    assert workspace.checkpoint("Update result") != first
