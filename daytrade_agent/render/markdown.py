from __future__ import annotations

import html
import re


def _inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(
        r"source_id:\s*([A-Za-z0-9_-]+)",
        r'<a class="evidence-link" href="#source-\1">원문 근거</a>', escaped,
    )

    def data_link(match: re.Match) -> str:
        key = match.group(1)
        target = "score-method" if key.startswith("score_") else f"data-{key}"
        return f'<a class="evidence-link" href="#{target}">데이터 근거</a>'

    return re.sub(r"data_key:\s*([A-Za-z0-9_-]+)", data_link, escaped)


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("#"):
            level = min(6, len(line) - len(line.lstrip("#")))
            text = line[level:].strip()
            output.append(f"<h{level}>{html.escape(text)}</h{level}>")
            index += 1
            continue
        if line.startswith(">"):
            output.append(f"<blockquote>{html.escape(line[1:].strip())}</blockquote>")
            index += 1
            continue
        if _is_table_line(line):
            table_lines = []
            while index < len(lines) and _is_table_line(lines[index]):
                table_lines.append(lines[index])
                index += 1
            output.append(_render_table(table_lines))
            continue
        if line.startswith("- "):
            items = []
            while index < len(lines) and lines[index].startswith("- "):
                items.append(lines[index][2:].strip())
                index += 1
            output.append("<ul>")
            output.extend(f"<li>{_inline(item)}</li>" for item in items)
            output.append("</ul>")
            continue
        output.append(f"<p>{_inline(line.strip())}</p>")
        index += 1
    return "\n".join(output)


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _render_table(lines: list[str]) -> str:
    rows = [_split_table(line) for line in lines]
    html_lines = ['<div class="table-scroll"><table>']
    if rows:
        html_lines.append("<thead><tr>")
        html_lines.extend(f"<th>{html.escape(cell)}</th>" for cell in rows[0])
        html_lines.append("</tr></thead><tbody>")
    for row in rows[2:] if len(rows) > 1 and set("".join(rows[1])) <= {"-", ":", " "} else rows[1:]:
        html_lines.append("<tr>")
        html_lines.extend(f"<td>{_inline(cell)}</td>" for cell in row)
        html_lines.append("</tr>")
    html_lines.append("</tbody></table></div>")
    return "\n".join(html_lines)


def _split_table(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]

