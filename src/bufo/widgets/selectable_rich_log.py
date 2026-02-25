"""RichLog variant with mouse text selection support."""

from __future__ import annotations

from rich.text import Text
from textual.selection import Selection
from textual.strip import Strip
from textual.widgets import RichLog


class SelectableRichLog(RichLog):
    """RichLog that exposes offsets for drag-selection and copy."""

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        if not self.lines:
            return None
        text = "\n".join(line.text.rstrip() for line in self.lines)
        return selection.extract(text), "\n"

    def selection_updated(self, selection: Selection | None) -> None:
        self._line_cache.clear()
        self.refresh()

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        content_y = scroll_y + y
        line = self._render_line(content_y, scroll_x, self.scrollable_content_region.width)
        return line.apply_style(self.rich_style).apply_offsets(scroll_x, content_y)

    def _render_line(self, y: int, scroll_x: int, width: int) -> Strip:
        if y >= len(self.lines):
            return Strip.blank(width, self.rich_style)

        selection = self.text_selection
        key = (y + self._start_line, scroll_x, width, self._widest_line_width)
        if selection is None and key in self._line_cache:
            return self._line_cache[key]

        source_line = self.lines[y]
        if selection is not None:
            if (select_span := selection.get_span(y)) is not None:
                start, end = select_span
                if end == -1:
                    end = len(source_line.text)
                text = Text.assemble(
                    *[(segment.text, segment.style) for segment in source_line if not segment.control]
                )
                selection_style = self.screen.get_component_rich_style("screen--selection")
                text.stylize(selection_style, start, end)
                source_line = Strip(text.render(self.app.console), source_line.cell_length)

        line = source_line.crop_extend(scroll_x, scroll_x + width, self.rich_style)
        if selection is None:
            self._line_cache[key] = line
        return line
