#!/usr/bin/env python3
"""Render docs/architecture.md into a paginated PDF specification.

    pip install reportlab
    python docs/build_pdf.py [source.md] [output.pdf]

The markdown file stays the single source of truth; this script handles the
subset it uses: headings, paragraphs, bullet and numbered lists, fenced code
blocks, pipe tables, horizontal rules, and inline code / bold / italic.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        HRFlowable,

        NextPageTemplate,
        PageBreak,
        PageTemplate,
        Paragraph,
        Preformatted,
        Spacer,
        Table,
        TableStyle,
    )
    from reportlab.platypus.tableofcontents import TableOfContents
except ImportError:  # pragma: no cover - dependency hint
    sys.exit("reportlab is required: pip install reportlab")

DOCS = Path(__file__).resolve().parent
SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else DOCS / "architecture.md"
OUTPUT = Path(sys.argv[2]) if len(sys.argv) > 2 else DOCS / "architecture.pdf"

PAGE = A4
MARGIN = 20 * mm
FRAME_WIDTH = PAGE[0] - 2 * MARGIN

INK = colors.HexColor("#16181d")
MUTED = colors.HexColor("#5f6773")
ACCENT = colors.HexColor("#4f46e5")
RULE = colors.HexColor("#d8dce2")
CODE_BG = colors.HexColor("#f5f6f8")
HEAD_BG = colors.HexColor("#eef0fe")


# --- styles -----------------------------------------------------------------


def build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    s: dict[str, ParagraphStyle] = {}

    s["title"] = ParagraphStyle(
        "title", parent=base["Title"], fontSize=26, leading=31, textColor=INK,
        spaceAfter=10,
    )
    s["subtitle"] = ParagraphStyle(
        "subtitle", parent=base["Normal"], fontSize=14, leading=19,
        alignment=TA_CENTER, textColor=ACCENT, spaceAfter=6,
    )
    s["cover"] = ParagraphStyle(
        "cover", parent=base["Normal"], fontSize=10.5, leading=15,
        alignment=TA_CENTER, textColor=MUTED,
    )
    # keepWithNext stops a heading being orphaned at the foot of a page. Do this
    # with the style, not KeepTogether: nesting a heading inside a wrapper hides
    # its TOC attributes from afterFlowable.
    s["h2"] = ParagraphStyle(
        "h2", parent=base["Heading1"], fontSize=15.5, leading=20, textColor=INK,
        spaceBefore=17, spaceAfter=7, keepWithNext=1,
    )
    s["h3"] = ParagraphStyle(
        "h3", parent=base["Heading2"], fontSize=11.5, leading=15, textColor=ACCENT,
        spaceBefore=12, spaceAfter=5, keepWithNext=1,
    )
    s["body"] = ParagraphStyle(
        "body", parent=base["BodyText"], fontSize=10, leading=15, textColor=INK,
        spaceAfter=7,
    )
    s["bullet"] = ParagraphStyle(
        "bullet", parent=s["body"], leftIndent=13, bulletIndent=3, spaceAfter=3,
    )
    s["code"] = ParagraphStyle(
        "code", parent=base["Code"], fontSize=7.6, leading=9.6, textColor=INK,
    )
    s["cell"] = ParagraphStyle(
        "cell", parent=base["BodyText"], fontSize=8.4, leading=11.4,
        textColor=INK, spaceAfter=0,
    )
    s["cellhead"] = ParagraphStyle(
        "cellhead", parent=s["cell"], fontName="Helvetica-Bold",
    )
    s["toc1"] = ParagraphStyle(
        "toc1", parent=base["Normal"], fontSize=10.5, leading=17,
        textColor=INK,
    )
    s["toc2"] = ParagraphStyle(
        "toc2", parent=base["Normal"], fontSize=9.5, leading=14, leftIndent=16,
        textColor=MUTED,
    )
    return s


# --- inline markdown --------------------------------------------------------

CODE_SPAN = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])")


def inline(text: str) -> str:
    """Markdown inline syntax -> reportlab's mini-HTML."""
    out = html.escape(text, quote=False)
    out = CODE_SPAN.sub(
        lambda m: f'<font face="Courier" size="9">{m.group(1)}</font>', out
    )
    out = BOLD.sub(r"<b>\1</b>", out)
    out = ITALIC.sub(r"<i>\1</i>", out)
    return out


# --- block parsing ----------------------------------------------------------


def code_block(lines: list[str], styles) -> Table:
    """A fenced block, boxed so it reads as a unit."""
    body = Preformatted("\n".join(lines) or " ", styles["code"])
    table = Table([[body]], colWidths=[FRAME_WIDTH])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
                ("BOX", (0, 0), (-1, -1), 0.4, RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def pipe_table(rows: list[list[str]], styles) -> Table:
    header, *body = rows
    # Weight columns by their widest cell, then clamp so no column collapses.
    widths = [max(len(row[i]) if i < len(row) else 0 for row in rows) for i in
              range(len(header))]
    floor = 0.6 * FRAME_WIDTH / len(header) / max(sum(widths), 1)
    scaled = [max(w / max(sum(widths), 1), floor) for w in widths]
    total = sum(scaled)
    col_widths = [FRAME_WIDTH * w / total for w in scaled]

    data = [[Paragraph(inline(c), styles["cellhead"]) for c in header]]
    for row in body:
        padded = row + [""] * (len(header) - len(row))
        data.append([Paragraph(inline(c), styles["cell"]) for c in padded])

    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                ("GRID", (0, 0), (-1, -1), 0.4, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def heading(text: str, level: int, styles) -> Paragraph:
    para = Paragraph(inline(text), styles[f"h{level}"])
    para.toc_level = level - 2  # h2 -> 0, h3 -> 1
    para.toc_text = text
    return para


def parse(markdown: str, styles) -> list:
    lines = markdown.splitlines()
    story: list = []
    cover: list = []
    i = 0
    seen_rule = False
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            text = " ".join(paragraph).strip()
            if text:
                target = cover if not seen_rule else story
                style = "cover" if not seen_rule else "body"
                target.append(Paragraph(inline(text), styles[style]))
            paragraph = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # fenced code
        if stripped.startswith("```"):
            flush_paragraph()
            i += 1
            block: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            story.append(code_block(block, styles))
            story.append(Spacer(1, 9))
            continue

        # pipe table
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = lines[i].strip()
                # skip the |---|---| separator
                if not set(row.replace("|", "").replace(" ", "")) <= {"-", ":"}:
                    rows.append(split_row(row))
                i += 1
            if rows:
                story.append(pipe_table(rows, styles))
                story.append(Spacer(1, 10))
            continue

        # horizontal rule: the first one ends the cover page
        if stripped in ("---", "***", "___"):
            flush_paragraph()
            if not seen_rule:
                seen_rule = True
            else:
                story.append(Spacer(1, 4))
                story.append(HRFlowable(width="100%", color=RULE, thickness=0.5))
                story.append(Spacer(1, 6))
            i += 1
            continue

        # headings
        match = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if match:
            flush_paragraph()
            level, text = len(match.group(1)), match.group(2)
            if level == 1:
                cover.append(Paragraph(inline(text), styles["title"]))
            elif level == 2 and not seen_rule:
                cover.append(Paragraph(inline(text), styles["subtitle"]))
            else:
                story.append(heading(text, min(max(level, 2), 3), styles))
            i += 1
            continue

        # lists
        bullet_match = re.match(r"^[-*]\s+(.*)$", stripped)
        number_match = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if bullet_match or number_match:
            flush_paragraph()
            items: list[Paragraph] = []
            while i < len(lines):
                current = lines[i].strip()
                bullet_match = re.match(r"^[-*]\s+(.*)$", current)
                number_match = re.match(r"^(\d+)\.\s+(.*)$", current)
                if not (bullet_match or number_match):
                    # a plain indented line continues the previous item
                    if current and lines[i].startswith((" ", "\t")) and items:
                        items[-1] = Paragraph(
                            f"{items[-1].text} {inline(current)}",
                            styles["bullet"],
                            bulletText=items[-1].bulletText,
                        )
                        i += 1
                        continue
                    break
                if bullet_match:
                    marker, text = "•", bullet_match.group(1)
                else:
                    assert number_match is not None
                    marker = f"{number_match.group(1)}."
                    text = number_match.group(2)
                items.append(
                    Paragraph(inline(text), styles["bullet"], bulletText=marker)
                )
                i += 1
            story.extend(items)
            story.append(Spacer(1, 7))
            continue

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        paragraph.append(stripped)
        i += 1

    flush_paragraph()
    return cover, story


# --- document ---------------------------------------------------------------


class SpecTemplate(BaseDocTemplate):
    """Adds a footer and collects TOC entries as headings are laid out."""

    def __init__(self, path: str, **kwargs) -> None:
        super().__init__(path, pagesize=PAGE, **kwargs)
        frame = Frame(
            MARGIN, MARGIN, FRAME_WIDTH, PAGE[1] - 2 * MARGIN, id="body"
        )
        self.addPageTemplates(
            [
                PageTemplate("cover", [frame]),
                PageTemplate("body", [frame], onPage=self.footer),
            ]
        )

    def footer(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.4)
        canvas.line(MARGIN, MARGIN - 6, PAGE[0] - MARGIN, MARGIN - 6)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(
            MARGIN, MARGIN - 16, "Collective AI Agent System — architecture"
        )
        canvas.drawRightString(
            PAGE[0] - MARGIN, MARGIN - 16, f"Page {doc.page - 1}"
        )
        canvas.restoreState()

    def afterFlowable(self, flowable) -> None:
        level = getattr(flowable, "toc_level", None)
        if level is None:
            return
        self.notify("TOCEntry", (level, getattr(flowable, "toc_text", ""), self.page))


def main() -> int:
    if not SOURCE.exists():
        sys.exit(f"source not found: {SOURCE}")

    styles = build_styles()
    cover, body = parse(SOURCE.read_text(encoding="utf-8"), styles)

    toc = TableOfContents()
    toc.levelStyles = [styles["toc1"], styles["toc2"]]

    story: list = [Spacer(1, 55 * mm)]
    story.extend(cover)
    story.append(NextPageTemplate("body"))
    story.append(PageBreak())
    # The TOC must stay a top-level story item: multiBuild only scans the top
    # level for indexing flowables, so nesting it silently leaves a placeholder.
    story.append(Paragraph("Contents", styles["h2"]))
    story.append(Spacer(1, 4))
    story.append(toc)
    story.append(PageBreak())
    story.extend(body)

    doc = SpecTemplate(
        str(OUTPUT),
        title="Collective AI Agent System — Architecture",
        author="Collective AI Agent System",
        subject="Unified multi-agent memory and cross-platform continuity",
    )
    # Two passes so the contents page can carry real page numbers.
    doc.multiBuild(story)
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
