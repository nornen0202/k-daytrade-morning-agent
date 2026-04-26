from __future__ import annotations

import html


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
            output.extend(f"<li>{html.escape(item)}</li>" for item in items)
            output.append("</ul>")
            continue
        output.append(f"<p>{html.escape(line.strip())}</p>")
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
        html_lines.extend(f"<td>{html.escape(cell)}</td>" for cell in row)
        html_lines.append("</tr>")
    html_lines.append("</tbody></table></div>")
    return "\n".join(html_lines)


def _split_table(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]

