#!/usr/bin/env python3
"""Undo damage that Notion's Markdown import leaves in a SKILL.md body (outside fenced code).
Usage: repair-notion-body.py <in> > out"""
import re, sys
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
FENCE_LANG = {"txt": "text"}  # Notion rewrites ```text as ```txt
def fix_span(code):
    if re.fullmatch(r"-[A-Za-z][\w-]*(?:\s.*)?", code):  # `--out <dir>` -> `-out <dir>`
        code = "-" + code
    if re.fullmatch(r"\*[^*].*\*\*", code):  # `**…**` -> `*…**`
        code = "*" + code
    return code
def fix_line(line):
    line = re.sub(r"(?<!`)`([^`\n]+)`(?!`)", lambda m: "`" + fix_span(m.group(1)) + "`", line)
    line = re.sub(r"\\([\[\]])", r"\1", line)  # \[ -> [
    return line
out, fence = [], None
for line in open(sys.argv[1], encoding="utf-8").read().split("\n"):
    m = FENCE.match(line)
    if fence:
        if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence): fence = None
        out.append(line); continue
    if m:
        fence = m.group(1)
        lang = line.strip()[len(fence):]
        out.append(line.replace(lang, FENCE_LANG.get(lang, lang), 1) if lang else line); continue
    out.append(fix_line(line))
sys.stdout.write("\n".join(out))
