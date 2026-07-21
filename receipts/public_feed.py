"""Create privacy-preserving public projections of local Receipts manifests.

The capture manifest is deliberately rich: it can include a working directory,
full command line, source paths, and transcript artifact names.  It is not a
safe thing to publish.  This module creates a one-way, alias-only projection
for an explicitly curated public feed.  It never mutates or uploads a source
manifest.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from .analysis import is_source_file
from .integrity import manifest_sha256, verify_manifest


PUBLIC_FORMAT = "receipts-public-feed/v1"
PUBLIC_SCHEMA_VERSION = 1
PUBLICATION_KINDS = {"curated-sample", "github-actions-demo", "manual"}
_SAFE_AGENTS = {"codex", "claude", "cursor", "other"}
_SAFE_RESULTS = {"passed", "failed", "unparsed"}
_EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)


def _parse_time(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or value == "unparsed":
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _offset_ms(value: object, started_at: object) -> int | None:
    timestamp = _parse_time(value)
    start = _parse_time(started_at)
    if timestamp is None or start is None:
        return None
    return max(0, round((timestamp - start).total_seconds() * 1000))


def _runner_label(command: object) -> str:
    """Return only a small runner category, never the original command."""
    text = str(command or "").lower()
    if "pytest" in text:
        return "pytest"
    if "unittest" in text:
        return "unittest"
    if "vitest" in text:
        return "vitest"
    if re.search(r"\bjest\b", text):
        return "jest"
    if "go test" in text:
        return "go test"
    if "cargo test" in text:
        return "cargo test"
    if re.search(r"\b(?:npm|pnpm|yarn)(?:\s+run)?\s+test\b", text):
        return "javascript test"
    if "make test" in text:
        return "make test"
    return "recorded test runner"


def _agent_changed_files(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    final = manifest.get("final", {})
    # Key presence matters: an empty M10 agent delta is meaningful and must not
    # silently fall back to the raw dirty-worktree diff.
    if "agent_changed_files" in final:
        return list(final.get("agent_changed_files") or [])
    return list(final.get("changed_files") or [])


def _source_paths(manifest: dict[str, Any]) -> list[str]:
    analysis_paths = [
        item.get("path")
        for item in manifest.get("analysis", {}).get("verification", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    ]
    if analysis_paths:
        return sorted(set(analysis_paths))
    return sorted(
        {
            item.get("path")
            for item in _agent_changed_files(manifest)
            if isinstance(item, dict) and isinstance(item.get("path"), str) and is_source_file(item["path"])
        }
    )


def _public_receipt_id(projection: dict[str, Any]) -> str:
    seed = copy.deepcopy(projection)
    seed["receipt"].pop("id", None)
    return f"receipt-{manifest_sha256(seed)[:16]}"


def _duration_ms(value: object) -> int:
    try:
        return max(0, round(float(value or 0) * 1000))
    except (TypeError, ValueError):
        return 0


def sanitize_manifest(
    manifest: dict[str, Any],
    *,
    publication_kind: str = "manual",
    published_at: str | None = None,
) -> dict[str, Any]:
    """Build a strict, separately hashed, public evidence projection.

    The projection intentionally contains neither original source paths nor a
    mapping back to them.  It retains relative ordering and deterministic
    verification facts so a public viewer can still make the useful claim:
    whether a changed source file had a passing test after its final edit.
    """
    if publication_kind not in PUBLICATION_KINDS:
        choices = ", ".join(sorted(PUBLICATION_KINDS))
        raise ValueError(f"unknown publication kind {publication_kind!r}; choose one of: {choices}")

    meta = manifest.get("meta", {})
    timeline = manifest.get("timeline", {})
    analysis = manifest.get("analysis", {})
    source_paths = _source_paths(manifest)
    aliases = {source: f"file-{index:03d}" for index, source in enumerate(source_paths, start=1)}
    changed_by_path = {
        item.get("path"): item
        for item in _agent_changed_files(manifest)
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    observations = {
        item.get("path"): item
        for item in timeline.get("file_changes", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    verification = {
        item.get("path"): item
        for item in analysis.get("verification", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    scope_paths = {
        item.get("path")
        for item in analysis.get("scope_drift", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    sensitive_paths = {
        item.get("path")
        for item in analysis.get("risk_hints", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    started_at = meta.get("started_at")

    files: list[dict[str, Any]] = []
    for source in source_paths:
        changed = changed_by_path.get(source, {})
        observed = observations.get(source, {})
        classified = verification.get(source, {})
        status = classified.get("status", "unparsed")
        if status not in {"verified", "indirectly_exercised", "never_executed", "unparsed"}:
            status = "unparsed"
        risks: list[str] = []
        if source in sensitive_paths:
            risks.append("sensitive_path")
        if source in scope_paths:
            risks.append("scope_drift")
        files.append(
            {
                "id": aliases[source],
                "additions": changed.get("additions") if isinstance(changed.get("additions"), int) else None,
                "deletions": changed.get("deletions") if isinstance(changed.get("deletions"), int) else None,
                "verification": status,
                "risk_categories": risks,
                "preexisting_at_start": bool(observed.get("preexisting_at_start", changed.get("preexisting_at_start", False))),
                "last_modified_offset_ms": _offset_ms(observed.get("last_modified_observed_at"), started_at),
            }
        )

    tests: list[dict[str, Any]] = []
    for index, run in enumerate(timeline.get("test_executions", []), start=1):
        if not isinstance(run, dict):
            continue
        result = run.get("result", "unparsed")
        tests.append(
            {
                "id": f"test-{index:03d}",
                "runner": _runner_label(run.get("command")),
                "result": result if result in _SAFE_RESULTS else "unparsed",
                "offset_ms": _offset_ms(run.get("timestamp"), started_at),
            }
        )

    agent = meta.get("agent")
    projection: dict[str, Any] = {
        "public_schema_version": PUBLIC_SCHEMA_VERSION,
        "format": PUBLIC_FORMAT,
        "receipt": {
            "id": "",
            "agent": agent if agent in _SAFE_AGENTS else "other",
            "duration_ms": _duration_ms(meta.get("duration_seconds")),
            "path_mode": "aliased",
            "time_mode": "relative_offsets_only",
        },
        "summary": {
            "command_count": int(timeline.get("command_count") or 0),
            "agent_changed_file_count": len(files),
            "test_run_count": len(tests),
            "never_executed_count": sum(item["verification"] == "never_executed" for item in files),
            "preexisting_dirty_count": len(meta.get("preexisting_dirty_paths") or []),
            "network_egress_observed": bool(analysis.get("network_egress")),
        },
        "files": files,
        "tests": tests,
        "publication": {
            "kind": publication_kind,
            "privacy": "source paths, task, commands, git data, and transcripts withheld",
        },
    }
    if published_at is not None:
        projection["publication"]["published_at"] = str(published_at)
    projection["receipt"]["id"] = _public_receipt_id(projection)
    projection["integrity"] = {"sha256": manifest_sha256(projection)}
    return projection


def verify_public_projection(projection: dict[str, Any]) -> tuple[bool, str]:
    """Verify a public projection's own hash and small structural contract."""
    if projection.get("format") != PUBLIC_FORMAT or projection.get("public_schema_version") != PUBLIC_SCHEMA_VERSION:
        return False, "not a Receipts public-feed projection"
    expected = projection.get("integrity", {}).get("sha256")
    if not isinstance(expected, str) or expected != manifest_sha256(projection):
        return False, "public projection sha256 mismatch"
    receipt = projection.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("path_mode") != "aliased":
        return False, "public projection does not use aliased paths"
    files = projection.get("files")
    if not isinstance(files, list) or any(
        not isinstance(item, dict) or not str(item.get("id", "")).startswith("file-")
        for item in files
    ):
        return False, "public projection file aliases are invalid"
    return True, "public projection sha256 verified"


def export_public_receipt(
    source_path: Path,
    output: Path,
    *,
    replay_output: Path | None = None,
    landing_href: str = "index.html",
    publication_kind: str = "manual",
    published_at: str | None = None,
    public_key: Path | None = None,
) -> tuple[dict[str, Any], str]:
    """Verify a private source receipt, then write its safe public derivative."""
    manifest = json.loads(source_path.read_text(encoding="utf-8"))
    source_ok, source_message = verify_manifest(manifest, source_path.parent, public_key)
    if not source_ok:
        raise ValueError(f"source receipt failed integrity verification: {source_message}")
    projection = sanitize_manifest(manifest, publication_kind=publication_kind, published_at=published_at)
    projection_ok, projection_message = verify_public_projection(projection)
    if not projection_ok:
        raise ValueError(f"public projection failed integrity verification: {projection_message}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(projection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if replay_output is not None:
        write_public_replay(projection, replay_output, landing_href=landing_href)
    return projection, source_message


_PUBLIC_REPLAY_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#080b19">
<title>Receipts · public evidence projection</title>
<style>
:root{color-scheme:dark;--ink:#f7f9ff;--soft:#c3cbe5;--muted:#8893b4;--cyan:#75e5ff;--mint:#72efc0;--amber:#ffd36b;--red:#ff7d9b;--night:#080b19;--line:rgba(220,232,255,.17);--glass:rgba(20,30,60,.68);--mono:"SFMono-Regular",Consolas,"Liberation Mono",monospace}*{box-sizing:border-box}body{min-width:320px;margin:0;background:radial-gradient(circle at 6% 4%,rgba(132,91,255,.25),transparent 28rem),radial-gradient(circle at 92% 13%,rgba(76,215,255,.18),transparent 30rem),#080b19;color:var(--ink);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}body:before{position:fixed;z-index:-1;inset:0;background-image:linear-gradient(rgba(155,179,240,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(155,179,240,.03) 1px,transparent 1px);background-size:44px 44px;content:""}.shell{width:min(1160px,calc(100% - 2.4rem));margin:auto}.nav{display:flex;align-items:center;gap:.8rem;margin:1rem 0;padding:.7rem 1rem;border:1px solid var(--line);border-radius:1rem;background:rgba(15,23,49,.68);backdrop-filter:blur(20px)}.brand{font-weight:850;letter-spacing:-.04em}.nav a{margin-left:auto;color:var(--cyan);font-size:.76rem;font-weight:800;text-decoration:none}.hero{display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,.6fr);gap:1rem;align-items:end;padding:3.5rem 0 1.4rem}.eyebrow{margin:0 0 .7rem;color:var(--cyan);font-size:.68rem;font-weight:850;letter-spacing:.13em;text-transform:uppercase}.hero h1{max-width:680px;margin:0;font-size:clamp(2.55rem,5vw,4.8rem);line-height:.97;letter-spacing:-.07em}.hero h1 span{color:#cbb9ff}.hero p{max-width:650px;color:var(--soft)}.badge{display:inline-flex;align-items:center;gap:.42rem;padding:.36rem .57rem;border:1px solid rgba(114,239,192,.35);border-radius:999px;background:rgba(114,239,192,.08);color:#c5f9df;font-size:.62rem;font-weight:850;letter-spacing:.07em;text-transform:uppercase}.badge:before{width:.42rem;height:.42rem;border-radius:50%;background:var(--mint);box-shadow:0 0 12px rgba(114,239,192,.68);content:""}.panel{border:1px solid var(--line);border-radius:1rem;background:linear-gradient(135deg,rgba(28,42,80,.72),rgba(11,17,38,.7));box-shadow:0 25px 70px rgba(0,0,0,.27);backdrop-filter:blur(20px)}.receipt{padding:1rem}.receipt p{margin:.25rem 0;color:var(--soft)}.receipt code{color:#dbe6ff;font:700 .7rem var(--mono)}.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;overflow:hidden;margin:1.1rem 0;border:1px solid var(--line);border-radius:1rem;background:var(--line)}.metric{padding:1.05rem;background:rgba(17,27,56,.74)}.metric b{display:block;font-size:1.7rem;line-height:1;letter-spacing:-.055em}.metric:last-child b{color:var(--red)}.metric span{display:block;margin-top:.35rem;color:var(--muted);font-size:.6rem;font-weight:800;letter-spacing:.07em;text-transform:uppercase}.workspace{display:grid;grid-template-columns:minmax(0,1fr) minmax(250px,.47fr);gap:1rem;padding-bottom:2.4rem}.head{display:flex;align-items:center;justify-content:space-between;gap:.8rem;padding:1rem;border-bottom:1px solid var(--line)}.head h2{margin:0;font-size:.96rem}.filters{display:flex;flex-wrap:wrap;gap:.4rem}.filter,.verify{padding:.45rem .6rem;border:1px solid var(--line);border-radius:.55rem;background:rgba(255,255,255,.04);color:var(--soft);font-size:.68rem;font-weight:800;cursor:pointer}.filter.active,.filter:hover,.verify:hover{border-color:rgba(117,229,255,.55);background:rgba(117,229,255,.1);color:white}.rows{display:grid;gap:.55rem;padding:1rem}.row{display:grid;grid-template-columns:10px minmax(0,1fr) auto;gap:.65rem;align-items:center;padding:.7rem;border:1px solid rgba(255,255,255,.06);border-radius:.7rem;background:rgba(255,255,255,.035)}.dot{width:9px;height:9px;border-radius:50%;background:var(--amber)}.row.verified .dot{background:var(--mint)}.row.never_executed{border-color:rgba(255,125,155,.38);background:rgba(255,125,155,.09)}.row.never_executed .dot{background:var(--red);box-shadow:0 0 0 4px rgba(255,125,155,.12)}.row code{overflow:hidden;font:800 .76rem var(--mono);text-overflow:ellipsis;white-space:nowrap}.row small{color:var(--muted);font-size:.64rem}.status{font-size:.65rem;font-weight:850;text-transform:uppercase}.verified .status{color:var(--mint)}.indirectly_exercised .status{color:var(--amber)}.never_executed .status{color:#ffb2c1}.side{padding:1rem}.side h2{margin:0 0 .7rem;font-size:.83rem}.side p,.side li{color:var(--soft);font-size:.75rem}.side ul{padding-left:1.1rem}.integrity{margin-top:1rem;padding:.8rem;border-left:2px solid var(--violet,#ae91ff);border-radius:0 .55rem .55rem 0;background:rgba(174,145,255,.08)}.integrity code{display:block;overflow:hidden;margin-top:.4rem;color:#dfe6ff;font:.65rem var(--mono);text-overflow:ellipsis}.timeline{display:grid;gap:.55rem;margin-top:1rem}.event{display:grid;grid-template-columns:52px 10px 1fr;gap:.55rem;align-items:center;padding:.45rem 0;border-bottom:1px solid rgba(255,255,255,.07)}.event:last-child{border:0}.event time{color:var(--muted);font:.65rem var(--mono)}.event i{width:8px;height:8px;border-radius:50%;background:var(--cyan)}.event.passed i{background:var(--mint)}.event.failed i{background:var(--red)}.event b{display:block;font-size:.72rem}.event span{color:var(--muted);font-size:.66rem}.footer{padding:1.35rem 0 2.4rem;color:var(--muted);font-size:.72rem;text-align:center}.ok{color:#c8fbe2}.bad{color:#ffd1da}@media(max-width:780px){.hero,.workspace{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}.metric:last-child{grid-column:span 2}.nav a{display:none}}@media(max-width:460px){.shell{width:min(100% - 1.2rem,1160px)}.hero{padding-top:2.2rem}.metrics{grid-template-columns:1fr}.metric:last-child{grid-column:auto}}
</style></head>
<body><div class="shell"><header class="nav"><span class="brand">▣ Receipts</span><span class="badge" id="mode">public evidence</span><a href="__LANDING_HREF__">Back to dashboard</a></header><main><section class="hero"><div><p class="eyebrow">Alias-only evidence projection</p><h1>Forensic facts,<br><span>without raw session data.</span></h1><p id="subtitle">Loading public projection…</p></div><aside class="panel receipt"><p class="eyebrow">Receipt identity</p><code id="receipt-id">loading</code><p id="published">Published details loading…</p></aside></section><section class="metrics" aria-label="Receipt metrics"><div class="metric"><b id="files">–</b><span>source aliases</span></div><div class="metric"><b id="tests">–</b><span>test runs</span></div><div class="metric"><b id="commands">–</b><span>commands observed</span></div><div class="metric"><b id="duration">–</b><span>duration</span></div><div class="metric"><b id="gaps">–</b><span>never executed</span></div></section><section class="workspace"><section class="panel" id="red-flag"><div class="head"><h2>Verification evidence</h2><div class="filters"><button class="filter active" data-filter="all">All</button><button class="filter" data-filter="red">Never executed</button><button class="filter" data-filter="risk">Flagged</button></div></div><div class="rows" id="files-list"></div></section><aside class="panel side"><h2>Published safely</h2><p>This viewer contains a separate, public projection—not the local session manifest.</p><ul><li>Source paths are stable aliases.</li><li>Task, terminal command, Git metadata, and transcript are withheld.</li><li>Event timing uses offsets only, not wall-clock timestamps.</li></ul><div class="integrity"><button class="verify" id="verify" type="button">Verify projection hash</button><span id="integrity-state">Ready for browser verification.</span><code id="hash">sha256 loading…</code></div><h2 style="margin-top:1.3rem">Recorded test order</h2><div class="timeline" id="timeline"></div></aside></section></main><footer class="footer">Portable public evidence · no raw transcript or private source-path mapping is embedded in this file.</footer></div><script id="public-receipt" type="application/json">__PUBLIC_RECEIPT_JSON__</script><script>
(() => { "use strict"; const receipt=JSON.parse(document.getElementById("public-receipt").textContent),$=id=>document.getElementById(id),label=s=>({verified:"verified",indirectly_exercised:"indirect coverage",never_executed:"never executed",unparsed:"unparsed"}[s]||s),ms=v=>v===null||v===undefined?"unparsed":`${(Number(v)/1000).toFixed(1)}s`,canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==="object"?Object.keys(v).sort().reduce((o,k)=>(o[k]=canonical(v[k]),o),{}):v,body=v=>{const copy={...v};delete copy.integrity;return JSON.stringify(canonical(copy));},hash=async v=>Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(body(v)))),x=>x.toString(16).padStart(2,"0")).join(""); let filter="all"; const summary=receipt.summary||{}, publication=receipt.publication||{}; $("receipt-id").textContent=receipt.receipt?.id||"public receipt"; $("subtitle").textContent=`${receipt.receipt?.agent||"other"} agent · ${ms(receipt.receipt?.duration_ms)} observed · details protected by an alias-only public projection`; $("published").textContent=publication.published_at?`Published ${publication.published_at} · ${publication.kind||"manual"}`:`${publication.kind||"manual"} · publication time withheld`; $("files").textContent=String(summary.agent_changed_file_count||0); $("tests").textContent=String(summary.test_run_count||0); $("commands").textContent=String(summary.command_count||0); $("duration").textContent=ms(receipt.receipt?.duration_ms); $("gaps").textContent=String(summary.never_executed_count||0); $("hash").textContent=`sha256 ${receipt.integrity?.sha256||"unavailable"}`;
 function renderFiles(){const holder=$("files-list");holder.replaceChildren();const files=(receipt.files||[]).filter(file=>filter==="all"||filter==="red"&&file.verification==="never_executed"||filter==="risk"&&(file.risk_categories||[]).length);if(!files.length){const empty=document.createElement("p");empty.textContent="No public evidence matches this filter.";holder.append(empty);return;}for(const file of files){const row=document.createElement("article");row.className=`row ${file.verification||"unparsed"}`;const dot=document.createElement("i");dot.className="dot";const text=document.createElement("div"),name=document.createElement("code"),detail=document.createElement("small");name.textContent=file.id;const risks=[...(file.risk_categories||[]),file.preexisting_at_start?"pre-existing boundary":""].filter(Boolean);detail.textContent=`+${file.additions??"?"} / −${file.deletions??"?"} · final observed edit ${ms(file.last_modified_offset_ms)}${risks.length?` · ${risks.join(", ")}`:""}`;text.append(name,detail);const status=document.createElement("span");status.className="status";status.textContent=label(file.verification);row.append(dot,text,status);holder.append(row);}}
 function renderTimeline(){const holder=$("timeline");holder.replaceChildren();for(const test of receipt.tests||[]){const row=document.createElement("div");row.className=`event ${test.result||"unparsed"}`;const time=document.createElement("time");time.textContent=ms(test.offset_ms);const dot=document.createElement("i"),body=document.createElement("div"),title=document.createElement("b"),detail=document.createElement("span");title.textContent=test.runner||"recorded test runner";detail.textContent=test.result||"unparsed";body.append(title,detail);row.append(time,dot,body);holder.append(row);}if(!holder.children.length){const empty=document.createElement("p");empty.textContent="No recorded test executions in this public projection.";holder.append(empty);}}
 document.querySelectorAll(".filter").forEach(button=>button.addEventListener("click",()=>{filter=button.dataset.filter;document.querySelectorAll(".filter").forEach(item=>item.classList.toggle("active",item===button));renderFiles();}));$("verify").addEventListener("click",async()=>{const state=$("integrity-state");try{const actual=await hash(receipt);if(actual===receipt.integrity?.sha256){state.textContent="Projection sha256 verified in this browser.";state.className="ok";}else{state.textContent="Hash mismatch — do not rely on this public object.";state.className="bad";}}catch(error){state.textContent="Web Crypto is unavailable in this browser.";state.className="bad";}});renderFiles();renderTimeline(); })();
</script></body></html>'''


def _validate_landing_href(landing_href: str) -> str:
    if not re.fullmatch(r"(?:\.\./)?index\.html(?:#[A-Za-z0-9_-]+)?", landing_href):
        raise ValueError("public replay landing href must be index.html or ../index.html")
    return landing_href


def render_public_replay(projection: dict[str, Any], *, landing_href: str = "index.html") -> str:
    """Render a self-contained viewer containing only a public projection."""
    valid, message = verify_public_projection(projection)
    if not valid:
        raise ValueError(f"cannot render invalid public projection: {message}")
    embedded = json.dumps(projection, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (
        _PUBLIC_REPLAY_TEMPLATE
        .replace("__LANDING_HREF__", _validate_landing_href(landing_href))
        .replace("__PUBLIC_RECEIPT_JSON__", embedded)
    )


def write_public_replay(projection: dict[str, Any], output: Path, *, landing_href: str = "index.html") -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_public_replay(projection, landing_href=landing_href), encoding="utf-8")
    return output
