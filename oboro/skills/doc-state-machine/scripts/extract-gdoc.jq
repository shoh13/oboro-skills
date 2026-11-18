# Google Docs API の documents.get の結果（MCP の read_doc の出力）から、sections.json の下書きを作成する。
# 使い方: jq -f extract-gdoc.jq <read_doc の出力.json> > sections.json
# 節は見出し（HEADING_1〜6）ごとに区切る。タブの冒頭で最初の見出しより前の本文は「（冒頭）」の節にする。
# 子タブも親タブの後に順に処理する。tab には「親 / 子」の形でタブの経路を記載する。
# 節の id は「<タブ ID>/<見出し ID>」、冒頭の節は「<タブ ID>/top」とする。見出し ID は原文の編集後も変化しないため、
# 再抽出しても既存の src が同じ節を指す。見出し ID はタブをまたいで重複することがあるため、タブ ID を前置する。
def ptext: [.elements[]? | (.textRun.content // "")] | join("") | rtrimstr("\n");
def block:
  if .paragraph then
    (.paragraph.paragraphStyle.namedStyleType // "NORMAL_TEXT") as $s
    | if ($s | startswith("HEADING_")) then
        {h: true, level: ($s | ltrimstr("HEADING_") | tonumber), hid: (.paragraph.paragraphStyle.headingId // ""), text: (.paragraph | ptext)}
      else
        {h: false, text: ((if .paragraph.bullet then ("  " * (.paragraph.bullet.nestingLevel // 0)) + "- " else "" end) + (.paragraph | ptext))}
      end
  elif .table then
    {h: false, text: ([.table.tableRows[] | "| " + ([.tableCells[] | [.content[]? | select(.paragraph) | .paragraph | ptext] | join(" / ")] | join(" | ")) + " |"] | join("\n"))}
  else empty end;
def tabs($path): .[]? | (.tabProperties.title) as $t | ($path + [$t]) as $p | {tab: ., path: $p}, (.childTabs | tabs($p));
(.content // .) as $doc
| ("https://docs.google.com/document/d/" + $doc.documentId + "/edit") as $base
| [ $doc.tabs | tabs([])
    | .path as $path | .tab.tabProperties.tabId as $tid
    | [.tab.documentTab.body.content[]? | block]
    | reduce .[] as $b ([{level: 0, hid: "", title: "（冒頭）", lines: []}];
        if $b.h then . + [{level: $b.level, hid: $b.hid, title: $b.text, lines: []}]
        else .[-1].lines += [$b.text] end)
    | .[]
    | . as $s
    | ($s.lines | map(select(test("\\S"))) | join("\n")) as $text
    | select($s.level > 0 or ($text | length) > 0)
    | {
        id: ($tid + "/" + (if $s.level == 0 then "top" else $s.hid end)),
        tab: ($path | join(" / ")),
        level: $s.level,
        title: (if ($s.title | test("\\S")) then $s.title else "（無題の見出し）" end),
        url: ($base + "?tab=" + $tid + (if $s.hid != "" then "#heading=" + $s.hid else "" end)),
        text: $text
      }
  ]
