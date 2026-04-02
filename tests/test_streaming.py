"""Test cases for Streaming Renderer."""

import pytest

from mini_agent.streaming import (
    StreamingRenderer,
    clear_line,
    erase_lines,
    move_cursor_up,
    render_streaming,
)


class TestStreamingRenderer:
    """Tests for StreamingRenderer class."""

    def test_empty_content(self):
        """Test handling of empty content."""
        renderer = StreamingRenderer()
        result = renderer.update("")
        assert result == ""
        assert renderer.stable_prefix == ""
        assert renderer.unstable_content == ""

    def test_single_incomplete_line(self):
        """Test a single line without newline (unstable)."""
        renderer = StreamingRenderer()
        result = renderer.update("test output")
        assert result == "test output"
        assert renderer.stable_prefix == ""
        assert renderer.unstable_content == "test output"

    def test_single_complete_line(self):
        """Test a single line with newline (stable)."""
        renderer = StreamingRenderer()
        result = renderer.update("test output\n")
        assert result == "test output\n"
        assert renderer.stable_prefix == "test output\n"
        assert renderer.unstable_content == ""

    def test_multiple_lines_last_incomplete(self):
        """Test multiple lines with last one incomplete."""
        renderer = StreamingRenderer()
        result = renderer.update("line1\nline2\nline3")
        assert result == "line1\nline2\nline3"
        assert renderer.stable_prefix == "line1\nline2\n"
        assert renderer.unstable_content == "line3"

    def test_multiple_lines_all_complete(self):
        """Test multiple lines, all complete."""
        renderer = StreamingRenderer()
        result = renderer.update("line1\nline2\nline3\n")
        assert result == "line1\nline2\nline3\n"
        assert renderer.stable_prefix == "line1\nline2\nline3\n"
        assert renderer.unstable_content == ""

    def test_incremental_update(self):
        """Test incremental updates to growing output."""
        renderer = StreamingRenderer()

        # Initial partial line
        result1 = renderer.update("test")
        assert result1 == "test"
        assert renderer.unstable_content == "test"
        assert renderer.stable_prefix == ""

        # Continue the line
        result2 = renderer.update("test output")
        assert result2 == "test output"
        assert renderer.unstable_content == "test output"

        # Complete the line
        result3 = renderer.update("test output\n")
        assert result3 == "test output\n"
        assert renderer.stable_prefix == "test output\n"
        assert renderer.unstable_content == ""

    def test_incremental_with_multiple_lines(self):
        """Test incremental updates with multiple lines."""
        renderer = StreamingRenderer()

        # First line complete
        renderer.update("line1\n")
        assert renderer.stable_prefix == "line1\n"

        # Second line incomplete
        result = renderer.update("line1\nline2")
        assert result == "line1\nline2"
        assert renderer.stable_prefix == "line1\n"
        assert renderer.unstable_content == "line2"

        # Second line completes
        result = renderer.update("line1\nline2\n")
        assert result == "line1\nline2\n"
        assert renderer.stable_prefix == "line1\nline2\n"
        assert renderer.unstable_content == ""

    def test_clear(self):
        """Test clearing the renderer."""
        renderer = StreamingRenderer()
        renderer.update("line1\nline2\n")
        assert renderer.stable_prefix == "line1\nline2\n"

        renderer.clear()
        assert renderer.stable_prefix == ""
        assert renderer.unstable_content == ""
        assert renderer.last_line_count == 0

    def test_render_returns_full_content(self):
        """Test that render() returns complete content."""
        renderer = StreamingRenderer()
        renderer.update("line1\nline2\nline3")

        # render() should return same as last update()
        result = renderer.render()
        assert result == "line1\nline2\nline3"

    def test_content_reset_detection(self):
        """Test detection of content reset (fewer lines than before)."""
        renderer = StreamingRenderer()

        # Start with multiple lines
        renderer.update("line1\nline2\nline3\n")
        assert renderer.last_line_count == 3

        # Simulate content reset - new content has fewer lines
        renderer.update("new1\n")
        assert renderer.stable_prefix == "new1\n"
        assert renderer.unstable_content == ""

    def test_preserves_stable_lines(self):
        """Test that stable lines are never re-rendered."""
        renderer = StreamingRenderer()

        # Build up stable content
        renderer.update("stable1\n")
        assert renderer.stable_prefix == "stable1\n"

        renderer.update("stable1\nstable2\n")
        assert renderer.stable_prefix == "stable1\nstable2\n"

        # Update unstable line multiple times
        renderer.update("stable1\nstable2\ngrowing...")
        renderer.update("stable1\nstable2\ngrowing... more")
        renderer.update("stable1\nstable2\ngrowing... complete")

        # Stable prefix should be unchanged
        assert renderer.stable_prefix == "stable1\nstable2\n"

    def test_finalize_with_newline(self):
        """Test finalizing unstable line with newline."""
        renderer = StreamingRenderer()

        renderer.update("test")
        assert renderer.unstable_content == "test"

        renderer.update("test\n")
        assert renderer.unstable_content == ""
        assert renderer.stable_prefix == "test\n"


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_clear_line(self):
        """Test clear_line function."""
        result = clear_line()
        assert result == "\r\033[K"

    def test_move_cursor_up(self):
        """Test move_cursor_up function."""
        result = move_cursor_up(3)
        assert result == "\033[3A"

    def test_erase_lines(self):
        """Test erase_lines function."""
        result = erase_lines(5)
        assert result == "\033[5A\033[K"


class TestRenderStreamingHelper:
    """Tests for render_streaming helper function."""

    def test_create_new_renderer(self):
        """Test creating renderer via helper."""
        result, renderer = render_streaming("test content\n")
        assert result == "test content\n"
        assert isinstance(renderer, StreamingRenderer)

    def test_update_existing_renderer(self):
        """Test updating existing renderer."""
        renderer = StreamingRenderer()
        renderer.update("existing\n")

        result, returned_renderer = render_streaming("existing\nupdate", renderer=renderer)
        assert returned_renderer is renderer
        assert result == "existing\nupdate"

    def test_incremental_rendering(self):
        """Test incremental rendering with helper."""
        renderer = None

        # Simulate streaming output
        chunks = ["test", "ing s", "tream", "ing\n", "line2\n", "line3"]

        for chunk in chunks:
            output, renderer = render_streaming(chunk, renderer=renderer)
            # Just verify no errors occur
            assert renderer is not None
