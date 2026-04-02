"""Streaming output renderer with stable prefix and unstable suffix pattern.

This module provides incremental rendering for long-running tasks like
npm test, pytest, etc., reducing visual flicker and improving UX.
"""

import sys
from dataclasses import dataclass, field


@dataclass
class StreamingRenderer:
    """Renders streaming output with stable prefix and unstable suffix.

    Lines that end with a newline are considered "stable" and will not
    be re-rendered. The last line (without a trailing newline) is
    considered "unstable" and will be updated on each render.

    This follows the Claude Code pattern for handling long-running
    command output with minimal visual disruption.
    """

    stable_prefix: str = field(default="")
    unstable_content: str = field(default="")
    last_line_count: int = 0

    def update(self, new_content: str) -> str:
        """Process new content and return the portion that needs re-rendering.

        Args:
            new_content: The complete accumulated content

        Returns:
            The portion that should be re-rendered (unstable lines)
        """
        if not new_content:
            return ""

        # Split into lines
        lines = new_content.split("\n")

        # Count complete lines (lines ending with \n are stable)
        # Note: split("\n") adds empty string after trailing \n, so adjust accordingly
        if new_content.endswith("\n"):
            complete_lines = len(lines) - 1  # Exclude empty string after trailing \n
        else:
            complete_lines = len(lines) - 1  # Last line is incomplete

        # If we have fewer complete lines than before, content was reset
        if complete_lines < self.last_line_count:
            self.stable_prefix = ""
            self.unstable_content = ""
            self.last_line_count = 0
            lines = new_content.split("\n")
            if new_content.endswith("\n"):
                complete_lines = len(lines) - 1
            else:
                complete_lines = len(lines) - 1
            # Handle the reset content directly and return
            if complete_lines > 0:
                self.stable_prefix = "\n".join(lines[:complete_lines])
                if self.stable_prefix:
                    self.stable_prefix += "\n"
            if not new_content.endswith("\n"):
                self.unstable_content = lines[-1] if lines else ""
            else:
                self.unstable_content = ""
            self.last_line_count = complete_lines
            return self.render()

        # Stable content: all complete lines
        if complete_lines > 0:
            # All lines except the last (potentially incomplete) one
            self.stable_prefix = "\n".join(lines[:complete_lines])
            if complete_lines > 0 and self.stable_prefix:
                self.stable_prefix += "\n"

        # Unstable content: the last line (may be growing or empty)
        if not new_content.endswith("\n"):
            # Last line is incomplete (still growing)
            self.unstable_content = lines[-1] if lines else ""
        else:
            # All content is complete
            self.unstable_content = ""

        self.last_line_count = complete_lines

        # Return what needs to be re-rendered
        return self.render()

    def render(self) -> str:
        """Return the complete rendered string.

        Returns:
            Full rendered output with stable prefix and current unstable content
        """
        result = self.stable_prefix
        if self.unstable_content:
            result += self.unstable_content
        return result

    def clear(self) -> None:
        """Clear all accumulated content."""
        self.stable_prefix = ""
        self.unstable_content = ""
        self.last_line_count = 0


def render_streaming(
    content: str,
    renderer: StreamingRenderer | None = None,
    clear_on_newline: bool = False,
) -> tuple[str, StreamingRenderer]:
    """Helper function to render streaming content.

    Args:
        content: New content to render
        renderer: Existing renderer to update (creates new if None)
        clear_on_newline: If True, clears screen and re-renders on newline

    Returns:
        Tuple of (rendered_output, renderer_instance)
    """
    if renderer is None:
        renderer = StreamingRenderer()

    rendered = renderer.update(content)

    # Optionally handle terminal clear for newline detection
    if clear_on_newline and "\n" in content:
        # Move cursor to beginning of line and clear
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    return rendered, renderer


def erase_lines(n: int) -> str:
    """Generate ANSI escape sequence to erase n lines.

    Args:
        n: Number of lines to erase

    Returns:
        ANSI escape sequence
    """
    return "\033[{}A\033[K".format(n)


def move_cursor_up(n: int) -> str:
    """Generate ANSI escape sequence to move cursor up n lines.

    Args:
        n: Number of lines to move up

    Returns:
        ANSI escape sequence
    """
    return "\033[{}A".format(n)


def clear_line() -> str:
    """Generate ANSI escape sequence to clear current line.

    Returns:
        ANSI escape sequence
    """
    return "\r\033[K"
