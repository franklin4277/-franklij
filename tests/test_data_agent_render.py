"""单元测试：渲染工具（不依赖 SQLBot，纯函数）"""
from mini_agent.render import (
    render_markdown_table,
    render_from_data_envelope,
    describe_chart,
    render_answer_md,
)


def test_render_table_basic():
    md = render_markdown_table(
        fields=["name", "score"],
        rows=[{"name": "A", "score": 90.5}, {"name": "B", "score": 80}],
        title="测试",
    )
    assert "**测试**" in md
    assert "| name | score |" in md
    assert "| --- | --- |" in md
    assert "| A | 90.50 |" in md
    assert "| B | 80 |" in md


def test_render_table_empty():
    assert "没有字段" in render_markdown_table([], [])
    assert "无数据" in render_from_data_envelope(None)


def test_render_table_truncation():
    rows = [{"x": i} for i in range(100)]
    md = render_markdown_table(["x"], rows, max_rows=10)
    assert "前 10 行，共 100 行" in md


def test_render_table_escape():
    md = render_markdown_table(["v"], [{"v": "a|b"}])
    assert "a\\|b" in md


def test_render_from_data_envelope():
    data = {
        "fields": ["a", "b"],
        "data": [{"a": 1, "b": 2}, {"a": 3, "b": 4}],
    }
    md = render_from_data_envelope(data)
    assert "| a | b |" in md
    assert "| 1 | 2 |" in md


def test_describe_chart():
    c = {"type": "bar", "title": "T", "axis": {"x": {"name": "X", "value": "x"}, "y": [{"name": "Y", "value": "y"}]}}
    s = describe_chart(c)
    assert "bar" in s and "T" in s and "X 轴: X" in s and "Y 轴: Y" in s


def test_describe_chart_empty():
    assert describe_chart(None) == ""
    assert describe_chart({}) == ""


def test_render_answer_md_success():
    raw = {
        "success": True,
        "title": "测试标题",
        "sql": "SELECT 1",
        "data": {"fields": ["x"], "data": [{"x": 1}]},
        "chart": {"type": "bar", "title": "T"},
        "image_url": "",
        "message": "",
    }
    md, chart_path = render_answer_md(raw, charts_dir="/tmp", chart_bytes_fn=lambda url: b"")
    assert "测试标题" in md
    assert "| x |" in md
    assert chart_path is None  # no image_url


def test_render_answer_md_failure():
    raw = {"success": False, "message": "无法生成 SQL"}
    md, _ = render_answer_md(raw, charts_dir="/tmp", chart_bytes_fn=lambda url: b"")
    assert "无法生成 SQL" in md


if __name__ == "__main__":
    test_render_table_basic()
    test_render_table_empty()
    test_render_table_truncation()
    test_render_table_escape()
    test_render_from_data_envelope()
    test_describe_chart()
    test_describe_chart_empty()
    test_render_answer_md_success()
    test_render_answer_md_failure()
    print("All render tests passed.")