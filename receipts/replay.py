"""Self-contained static HTML replay renderer."""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Any


def render_replay(manifest: dict[str, Any]) -> str:
    embedded = json.dumps(manifest, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Receipts session replay</title>
<style>
:root{{color-scheme:dark}}body{{margin:0;background:#0b1020;color:#e5e7eb;font:15px ui-sans-serif,system-ui,sans-serif}}main{{max-width:1050px;margin:auto;padding:42px 24px}}h1{{font-size:28px;margin:0 0 6px}}.sub{{color:#9ca3af}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:25px 0}}.stat,.event,.flag{{background:#121a30;border:1px solid #253252;border-radius:10px;padding:14px}}.event{{margin:9px 0}}.time{{color:#7dd3fc;font-family:ui-monospace,monospace;font-size:12px}}.tag{{display:inline-block;border-radius:20px;padding:3px 8px;font-size:12px;background:#26375f;color:#bfdbfe}}.red{{border-color:#7f1d1d;background:#250f18}}.amber{{border-color:#78350f;background:#23170c}}code{{color:#c4b5fd;word-break:break-word}}details{{margin-top:22px}}pre{{white-space:pre-wrap;word-break:break-word;color:#cbd5e1}}</style></head>
<body><main><h1>🧾 Receipts session replay</h1><div class="sub" id="subtitle"></div><div class="grid" id="stats"></div><h2>Review flags</h2><div id="flags"></div><h2>Evidence timeline</h2><div id="timeline"></div><details><summary>Embedded manifest</summary><pre id="raw"></pre></details></main>
<script id="manifest" type="application/json">{embedded}</script><script>
const m=JSON.parse(document.getElementById('manifest').textContent), q=s=>document.querySelector(s), e=(tag,text,cls='')=>{{const n=document.createElement(tag);n.className=cls;n.textContent=text;return n}};
q('#subtitle').textContent=`${{m.meta.agent}} · ${{m.meta.session_id}} · ${{m.meta.git_branch||'no branch'}}`;
for(const [k,v] of [['Task',m.meta.task||'not recorded'],['Duration',`${{Math.round(m.meta.duration_seconds||0)}}s`],['Files changed',(m.final.changed_files||[]).length],['Test runs',(m.timeline.test_executions||[]).length]]){{let n=e('div','', 'stat');n.append(e('div',k,'sub'),e('strong',String(v)));q('#stats').append(n)}}
const flags=[...(m.analysis.scope_drift||[]).map(x=>['🔴 '+x.path+' — scope drift (heuristic)','red']),...(m.analysis.risk_hints||[]).map(x=>['⚠️ '+x.path+' — '+x.reason,'amber']),...(m.analysis.network_egress||[]).map(x=>['⚠️ network: '+x.command,'amber'])];
if(!flags.length)q('#flags').append(e('div','No flags recorded.','event'));for(const [text,cls] of flags)q('#flags').append(e('div',text,'flag '+cls));
const events=[...(m.timeline.file_changes||[]).map(x=>({{time:x.last_modified_observed_at,type:'file changed',text:x.path}})),...(m.timeline.test_executions||[]).map(x=>({{time:x.timestamp,type:'test '+x.result,text:x.command+(x.summary?' — '+x.summary:'')}})),...(m.timeline.notable_commands||[]).map(x=>({{time:x.timestamp,type:x.kind,text:x.command}}))].sort((a,b)=>String(a.time).localeCompare(String(b.time)));
for(const x of events){{let n=e('div','', 'event');n.append(e('div',x.time||'unparsed','time'),e('div',x.type,'tag'),e('div',x.text));q('#timeline').append(n)}}q('#raw').textContent=JSON.stringify(m,null,2);
</script></body></html>"""


def write_replay(manifest: dict[str, Any], output: Path, open_browser: bool = True) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_replay(manifest), encoding="utf-8")
    if open_browser:
        try:
            webbrowser.open(output.resolve().as_uri())
        except OSError:
            pass
    return output
