"""Render semantic XML tags to Rich console markup.

Color scheme: GitHub Dark theme
  - heading:    #e6edf3 (bold white)
  - subheading: #7ee787 (green)
  - code:       #a5d6ff on #161b22 (light blue on dark bg)
  - emphasis:   #d2a8ff (purple)
  - warning:    #d29922 (orange-yellow)
  - note:       #8b949e (gray)
  - list item:  #8b949e bullet + #e6edf3 text
  - separator:  #30363d (dark gray)
"""

import re

from rich.syntax import Syntax

# GitHub Dark palette mapped to closest ANSI/Rich styles
_H = "bold white"                          # heading: #e6edf3
_SH = "bold #7ee787"                       # subheading: green
_CODE = "#a5d6ff"                          # inline code: light blue
_CODE_BORDER = "#30363d"                   # code block border
_EM = "italic #d2a8ff"                     # emphasis: purple
_WARN = "#d29922"                          # warning: orange-yellow
_NOTE = "#8b949e"                          # note: gray
_BULLET = "#8b949e"                        # list bullet: gray
_SEP = "#30363d"                           # separator: dark gray

_CODE_BLOCK_RE = re.compile(r'<code\s+lang="([^"]*)">(.*?)</code>', re.DOTALL)


def render_semantic(text: str) -> list:
    """Convert semantic XML tags to a list of Rich renderables.

    Returns a list of strings (Rich markup) and Syntax objects (for code blocks).
    Use print_renderables() to display them.
    """
    # First, extract code blocks and replace with placeholders
    code_blocks: list[tuple[str, str]] = []

    def _extract_code_block(m: re.Match) -> str:
        lang = m.group(1) or "text"
        code = m.group(2).strip()
        idx = len(code_blocks)
        code_blocks.append((lang, code))
        return f"\n__CODE_BLOCK_{idx}__\n"

    text = _CODE_BLOCK_RE.sub(_extract_code_block, text)

    # Separator (self-closing and paired)
    sep_line = f"[{_SEP}]{'─' * 35}[/{_SEP}]"
    text = re.sub(r"<separator\s*/>", sep_line, text)
    text = re.sub(r"<separator>\s*</separator>", sep_line, text)

    # Inline code
    text = re.sub(r"<code>(.*?)</code>", rf"[{_CODE}]\1[/{_CODE}]", text)

    # Headings
    text = re.sub(r"<heading>(.*?)</heading>", rf"\n[{_H}]\1[/{_H}]\n", text)
    text = re.sub(r"<subheading>(.*?)</subheading>", rf"\n[{_SH}]\1[/{_SH}]\n", text)

    # Emphasis
    text = re.sub(r"<emphasis>(.*?)</emphasis>", rf"[{_EM}]\1[/{_EM}]", text)

    # Warning and note
    text = re.sub(r"<warning>(.*?)</warning>", rf"[{_WARN}]⚠ \1[/{_WARN}]", text)
    text = re.sub(r"<note>(.*?)</note>", rf"[{_NOTE}]ℹ \1[/{_NOTE}]", text)

    # List items (process items first, then strip list wrapper)
    text = re.sub(r"<item>(.*?)</item>", rf"  [{_BULLET}]•[/{_BULLET}] \1", text)
    text = re.sub(r"</?list>", "", text)

    # Clean up any remaining tags
    text = re.sub(
        r"</?(?:heading|subheading|emphasis|warning|note|separator|code|list|item)[^>]*>", "", text
    )

    # Clean up excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    # Split on code block placeholders and interleave with Syntax objects
    if not code_blocks:
        return [text]

    renderables: list = []
    parts = re.split(r"__CODE_BLOCK_(\d+)__", text)
    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Text segment
            stripped = part.strip()
            if stripped:
                renderables.append(stripped)
        else:
            # Code block index
            idx = int(part)
            lang, code = code_blocks[idx]
            renderables.append(
                Syntax(code, lang, theme="github-dark", word_wrap=True, padding=(0, 1))
            )
    return renderables


def print_renderables(console, renderables: list) -> None:
    """Print a list of renderables (strings and Syntax objects) to the console."""
    for r in renderables:
        console.print(r)
