"""T6:write_artifact 路径穿越防护。"""
import pytest

from workflow_chain.tools import write_artifact


def test_traversal_rejected(tmp_path):
    with pytest.raises(PermissionError):
        write_artifact(str(tmp_path), "../evil.txt", "boom")


def test_absolute_path_rejected(tmp_path):
    with pytest.raises(PermissionError):
        write_artifact(str(tmp_path), "C:/Windows/evil.txt", "boom")
    with pytest.raises(PermissionError):
        write_artifact(str(tmp_path), "/etc/passwd", "boom")


def test_nested_relative_ok(tmp_path):
    res = write_artifact(str(tmp_path), "scaffold/index.html", "<h1>ok</h1>")
    assert (tmp_path / "scaffold" / "index.html").read_text("utf-8") == "<h1>ok</h1>"
    assert res["bytes"] == len("<h1>ok</h1>".encode("utf-8"))
    assert res["path"].endswith("index.html")


def test_unicode_content(tmp_path):
    write_artifact(str(tmp_path), "a/b.md", "# 中文标题")
    assert (tmp_path / "a" / "b.md").read_text("utf-8") == "# 中文标题"
