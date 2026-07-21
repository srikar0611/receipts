"use strict";

const vscode = require("vscode");
const path = require("path");
const {
  durationLabel,
  safeRelativePath,
  safeWorkspaceDirectory,
  statusInfo,
  summaryFromManifest,
  treeDescription
} = require("./lib/receipt-model");

const decoder = new TextDecoder("utf-8");
const MAX_MANIFEST_BYTES = 5 * 1024 * 1024;
const MAX_MANIFESTS_PER_WORKSPACE = 100;

class SessionItem extends vscode.TreeItem {
  constructor(record) {
    super(record.summary.valid ? record.summary.task : record.summary.manifestName, vscode.TreeItemCollapsibleState.Collapsed);
    this.record = record;
    this.contextValue = "receiptsSession";
    this.description = treeDescription(record.summary);
    this.tooltip = record.summary.valid
      ? record.summary.manifestName + "\n" + treeDescription(record.summary)
      : record.summary.manifestName + "\n" + record.summary.error;
    const dangerous = record.summary.valid && record.summary.neverExecutedCount > 0;
    this.iconPath = new vscode.ThemeIcon(
      dangerous ? "error" : "pass",
      new vscode.ThemeColor(dangerous ? "testing.iconFailed" : "testing.iconPassed")
    );
    this.command = { command: "receipts.openWorkbench", title: "Open Receipts evidence workbench", arguments: [this] };
  }
}

class EvidenceFileItem extends vscode.TreeItem {
  constructor(session, file) {
    super(file.path, vscode.TreeItemCollapsibleState.None);
    this.session = session;
    this.file = file;
    this.contextValue = "receiptsFile";
    const info = statusInfo(file.status);
    this.description = info.label;
    this.tooltip = [file.path, info.detail, file.scopeDrift ? "Scope-drift heuristic flag." : "", file.sensitive ? "Sensitive-path risk hint." : ""]
      .filter(Boolean).join("\n");
    const iconName = info.severity === "danger" ? "error" : info.severity === "warning" ? "warning" : info.severity === "good" ? "pass" : "question";
    const color = info.severity === "danger" ? "testing.iconFailed" : info.severity === "warning" ? "list.warningForeground" : info.severity === "good" ? "testing.iconPassed" : "disabledForeground";
    this.iconPath = new vscode.ThemeIcon(iconName, new vscode.ThemeColor(color));
    this.command = { command: "receipts.openFile", title: "Open evidence file", arguments: [this] };
  }
}

class EmptyItem extends vscode.TreeItem {
  constructor(label, detail) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.description = detail;
    this.tooltip = label + "\n" + detail;
    this.contextValue = "receiptsEmpty";
    this.iconPath = new vscode.ThemeIcon("info");
  }
}

class ReceiptsProvider {
  constructor(statusBar) {
    this.statusBar = statusBar;
    this.records = [];
    this.loaded = false;
    this.events = new vscode.EventEmitter();
    this.onDidChangeTreeData = this.events.event;
  }

  refresh() {
    this.loaded = false;
    this.records = [];
    this.statusBar.hide();
    this.events.fire();
  }

  async recordsForWorkspace() {
    if (this.loaded) {
      return this.records;
    }
    const records = [];
    const limit = vscode.workspace.getConfiguration("receipts").get("maxSessions", 25);
    for (const folder of vscode.workspace.workspaceFolders || []) {
      const root = vscode.Uri.joinPath(folder.uri, ".receipts");
      for (const uri of (await findManifests(root, 4)).slice(0, MAX_MANIFESTS_PER_WORKSPACE)) {
        records.push(await readRecord(uri, folder.uri));
      }
    }
    records.sort((a, b) => b.modified - a.modified);
    this.records = records.slice(0, limit);
    this.loaded = true;
    this.updateStatusBar();
    return this.records;
  }

  async latest() {
    const records = await this.recordsForWorkspace();
    return records[0] || null;
  }

  updateStatusBar() {
    const record = this.records[0];
    if (!record || !record.summary.valid) {
      this.statusBar.hide();
      return;
    }
    const count = record.summary.neverExecutedCount;
    this.statusBar.text = count ? "$(error) Receipts: " + count + " NEVER EXECUTED" : "$(verified) Receipts: evidence recorded";
    this.statusBar.tooltip = record.summary.task + "\n" + treeDescription(record.summary);
    this.statusBar.backgroundColor = count ? new vscode.ThemeColor("statusBarItem.errorBackground") : undefined;
    this.statusBar.show();
  }

  async getChildren(element) {
    if (element instanceof SessionItem) {
      if (!element.record.summary.valid) {
        return [new EmptyItem("Malformed receipt", element.record.summary.error)];
      }
      const files = element.record.summary.files;
      return files.length ? files.map((file) => new EvidenceFileItem(element, file)) : [
        new EmptyItem("No agent-attributed files", "The manifest contains no agent-attributed changed files.")
      ];
    }
    if (element) {
      return [];
    }
    const records = await this.recordsForWorkspace();
    return records.length ? records.map((record) => new SessionItem(record)) : [
      new EmptyItem("No recorded receipt found", "Run receipts demo --live or receipts run -- <agent command>, then refresh this view.")
    ];
  }
}

async function findManifests(directory, depth) {
  try {
    const found = [];
    for (const entry of await vscode.workspace.fs.readDirectory(directory)) {
      const name = entry[0];
      const type = entry[1];
      const child = vscode.Uri.joinPath(directory, name);
      if (type === vscode.FileType.File && /^session-.+\.json$/i.test(name)) {
        found.push(child);
      } else if (type === vscode.FileType.Directory && depth > 0 && name !== "keys") {
        found.push(...await findManifests(child, depth - 1));
      }
    }
    return found.slice(0, MAX_MANIFESTS_PER_WORKSPACE);
  } catch {
    return [];
  }
}

async function readRecord(uri, workspaceUri) {
  let modified = 0;
  try {
    const stat = await vscode.workspace.fs.stat(uri);
    modified = stat.mtime;
    if (stat.size > MAX_MANIFEST_BYTES) {
      return {
        uri,
        workspaceUri,
        modified,
        manifest: null,
        summary: { valid: false, manifestPath: uri.fsPath, manifestName: path.basename(uri.fsPath), error: "Manifest exceeds the 5 MB extension safety limit." }
      };
    }
  } catch {
    // The receipt may have disappeared after discovery.
  }
  try {
    const manifest = JSON.parse(decoder.decode(await vscode.workspace.fs.readFile(uri)));
    return { uri, workspaceUri, modified, manifest, summary: summaryFromManifest(manifest, uri.fsPath) };
  } catch (error) {
    return {
      uri,
      workspaceUri,
      modified,
      manifest: null,
      summary: { valid: false, manifestPath: uri.fsPath, manifestName: path.basename(uri.fsPath), error: "Could not parse JSON: " + String(error.message || error) }
    };
  }
}

function shellQuote(value) {
  const text = String(value);
  if (process.platform === "win32") {
    return '"' + text.replace(/"/g, '""') + '"';
  }
  return "'" + text.replace(/'/g, "'\\''") + "'";
}

function cliTask(title, argumentsList, workspaceUri) {
  const executable = vscode.workspace.getConfiguration("receipts").get("command", "receipts");
  const execution = new vscode.ProcessExecution(executable, argumentsList, {
    cwd: workspaceUri ? workspaceUri.fsPath : undefined
  });
  const task = new vscode.Task(
    { type: "receipts", action: title },
    workspaceUri ? vscode.TaskScope.Workspace : vscode.TaskScope.Global,
    title,
    "Receipts",
    execution,
    []
  );
  return vscode.tasks.executeTask(task);
}

function sessionFrom(argument) {
  if (argument instanceof SessionItem) {
    return argument;
  }
  if (argument instanceof EvidenceFileItem) {
    return argument.session;
  }
  return null;
}

async function resolveSession(provider, argument) {
  const existing = sessionFrom(argument);
  if (existing) {
    return existing;
  }
  const latest = await provider.latest();
  return latest ? new SessionItem(latest) : null;
}

function escapeHtml(value) {
  return String(value === null || value === undefined ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function compactHash(value) {
  return value && value.length > 12 ? value.slice(0, 8) + "…" + value.slice(-4) : value || "not recorded";
}

function metric(value, label, extra) {
  return '<section class="metric ' + (extra || "") + '"><strong>' + escapeHtml(value === null ? "—" : value) + '</strong><span>' + escapeHtml(label) + "</span></section>";
}

function badge(status) {
  const info = statusInfo(status);
  return '<span class="badge ' + info.severity + '">' + escapeHtml(info.label) + "</span>";
}

const STYLE = [
  ":root{color-scheme:dark;--bg:#080b19;--panel:rgba(18,32,57,.86);--line:rgba(119,210,255,.22);--ink:#eef5ff;--muted:#9eafc9;--cyan:#67d5ff;--green:#65e7b1;--amber:#f6c85e;--red:#ff7187}",
  "*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 8% 0%,#14264d 0,transparent 37%),radial-gradient(circle at 92% 25%,#142b42 0,transparent 35%),var(--bg);color:var(--ink);font:14px/1.5 var(--vscode-font-family,system-ui,sans-serif)}",
  ".shell{max-width:1180px;margin:0 auto;padding:34px clamp(20px,4vw,56px) 56px}.topbar,.hero,.panel-heading,.metrics,.notes{display:flex;gap:20px}.topbar{justify-content:space-between;align-items:flex-start;margin-bottom:28px}.eyebrow,.kicker,.integrity-label{margin:0;color:var(--cyan);letter-spacing:.13em;font-size:11px;font-weight:800}.pulse{display:inline-block;width:8px;height:8px;border-radius:99px;margin-right:8px;background:var(--green);box-shadow:0 0 16px var(--green)}h1,h2,h3,p{margin-top:0}h1{margin-bottom:0;font-size:30px;letter-spacing:-.04em}h1 span{color:var(--cyan)}h2{margin:5px 0 7px;font-size:25px;letter-spacing:-.03em}code{font-family:var(--vscode-editor-font-family,ui-monospace,monospace);font-size:.92em}",
  ".integrity{min-width:190px;padding:13px 15px;border:1px solid var(--line);background:rgba(9,19,37,.7);border-radius:15px}.integrity strong,.integrity code,.integrity small{display:block}.integrity code{color:var(--amber);margin-top:2px}.integrity small{color:var(--muted);margin-top:3px}.glass{border:1px solid var(--line);background:linear-gradient(135deg,rgba(27,51,85,.84),rgba(17,27,56,.88));box-shadow:0 18px 55px rgba(0,0,0,.25);border-radius:22px}.hero{justify-content:space-between;align-items:center;padding:28px}.hero p{margin-bottom:0;color:var(--muted)}.actions{display:flex;flex-wrap:wrap;gap:9px;justify-content:flex-end}",
  "button{cursor:pointer;border:1px solid rgba(126,207,255,.35);background:rgba(19,40,68,.78);color:var(--ink);padding:9px 12px;border-radius:10px;font:inherit;font-weight:700}button:hover{border-color:var(--cyan);background:rgba(40,80,115,.8)}button.primary{background:linear-gradient(135deg,#65d6fb,#96a9ff);border-color:transparent;color:#07121f}button.ghost{color:var(--cyan);background:transparent}.metrics{margin:18px 0}.metric{flex:1;min-width:120px;padding:17px;border:1px solid rgba(119,210,255,.14);border-radius:16px;background:rgba(13,22,44,.6)}.metric strong{display:block;color:var(--cyan);font-size:27px;line-height:1}.metric span{color:var(--muted);font-size:10px;font-weight:800;letter-spacing:.09em}.metric.danger strong{color:var(--red)}",
  ".notice{margin:18px 0;padding:14px 16px;border-left:3px solid var(--amber);color:#d9e5f7;background:rgba(246,200,94,.08);border-radius:0 12px 12px 0}.attribution{border-left-color:var(--cyan);background:rgba(103,213,255,.08)}.evidence-panel{padding:25px}.panel-heading{align-items:center;justify-content:space-between}.panel-heading h2{margin-bottom:0}.file-list{margin-top:19px;border-top:1px solid rgba(119,210,255,.13)}.file-row{width:100%;display:flex;text-align:left;align-items:center;gap:12px;border:0;border-bottom:1px solid rgba(119,210,255,.13);border-radius:0;padding:15px 5px;background:transparent}.file-row:hover{background:rgba(103,213,255,.08)}",
  ".dot,.inline-dot{flex:none;display:inline-block;width:10px;height:10px;border-radius:50%}.dot.good,.inline-dot.good{background:var(--green);box-shadow:0 0 12px rgba(101,231,177,.65)}.dot.warning,.inline-dot.warning{background:var(--amber);box-shadow:0 0 12px rgba(246,200,94,.55)}.dot.danger,.inline-dot.danger{background:var(--red);box-shadow:0 0 12px rgba(255,113,135,.55)}.dot.muted{background:var(--muted)}.file-copy{min-width:0;flex:1}.file-copy code{color:#e7f2ff}.evidence{display:block;overflow:hidden;margin-top:3px;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.file-state{display:flex;flex-direction:column;align-items:flex-end;gap:5px}",
  ".badge{padding:3px 7px;border-radius:999px;font-size:10px;font-weight:800;letter-spacing:.04em;white-space:nowrap}.badge.good{color:var(--green);background:rgba(101,231,177,.12)}.badge.warning{color:var(--amber);background:rgba(246,200,94,.12)}.badge.danger{color:var(--red);background:rgba(255,113,135,.12)}.badge.muted{color:var(--muted);background:rgba(158,175,201,.12)}.flags{display:flex;gap:4px;justify-content:flex-end;flex-wrap:wrap}.flag{padding:1px 5px;border-radius:4px;color:var(--muted);font-size:10px;font-weight:600}.flag.danger{color:#ffc0ca;background:rgba(255,113,135,.12)}.flag.warning{color:#ffe2a1;background:rgba(246,200,94,.12)}.notes{margin-top:18px}.notes article{flex:1;padding:4px 12px;color:var(--muted)}.notes h3{color:var(--ink);margin-bottom:4px;font-size:13px}.notes p{margin-bottom:0}.empty{max-width:650px}",
  "@media(max-width:720px){.topbar,.hero,.panel-heading,.metrics,.notes{flex-direction:column}.integrity{width:100%}.actions{justify-content:flex-start}.metric{width:100%}.file-row{align-items:flex-start}.file-state{align-items:flex-start}}"
].join("");

function htmlFor(summary, nonce) {
  if (!summary.valid) {
    return '<!doctype html><html><head>' + head(nonce) + '</head><body><main class="shell empty"><p class="eyebrow">LOCAL EVIDENCE</p><h1>Malformed receipt</h1><p>' + escapeHtml(summary.error) + '</p><p class="muted">Receipts will not guess from an invalid manifest.</p></main></body></html>';
  }
  const rows = summary.files.map((file) => {
    const flags = (file.scopeDrift ? '<span class="flag danger">scope drift (heuristic)</span>' : "") +
      (file.sensitive ? '<span class="flag warning">sensitive path</span>' : "") +
      (file.preexistingAtStart ? '<span class="flag muted">pre-existing at start</span>' : "");
    const evidence = file.command
      ? '<span class="evidence">Evidence: <code>' + escapeHtml(file.command) + '</code></span>'
      : '<span class="evidence">Evidence: not confidently parsed</span>';
    return '<button class="file-row" data-action="open-file" data-path="' + encodeURIComponent(file.path) + '"><span class="dot ' + statusInfo(file.status).severity + '"></span><span class="file-copy"><code>' + escapeHtml(file.path) + '</code>' + evidence + '</span><span class="file-state">' + badge(file.status) + '<span class="flags">' + flags + '</span></span></button>';
  }).join("") || '<div class="notice">No stored verification entries matched agent-attributed changed files.</div>';
  const attribution = summary.preexistingDirtyCount !== null && summary.preexistingDirtyCount > 0
    ? '<div class="notice attribution"><strong>Attribution boundary:</strong> ' + escapeHtml(summary.preexistingDirtyCount) + ' path(s) were already dirty at recording start. They are not counted as agent work unless they changed during the session.</div>'
    : "";
  const otherChanges = summary.otherAgentChangedCount > 0
    ? '<div class="notice"><strong>Other agent-attributed changes:</strong> ' + escapeHtml(summary.otherAgentChangedCount) + ' file(s) have no stored verification-analysis entry, so Receipts does not label them as unparsed.</div>'
    : "";
  const signature = summary.signaturePresent ? "signature recorded — use Verify to validate it" : "unsigned receipt";
  return '<!doctype html><html lang="en"><head>' + head(nonce) + '</head><body><main class="shell">' +
    '<header class="topbar"><div><p class="eyebrow"><span class="pulse"></span> LOCAL EVIDENCE · NOTHING LEAVES THIS WORKSPACE</p><h1>Receipts <span>Evidence Workbench</span></h1></div>' +
    '<div class="integrity"><span class="integrity-label">INTEGRITY</span><strong>Not verified in VS Code</strong><code>' + escapeHtml(compactHash(summary.integrityHash)) + '</code><small>' + escapeHtml(signature) + '</small></div></header>' +
    '<section class="hero glass"><div><span class="kicker">AI SESSION TRUST CARD</span><h2>' + escapeHtml(summary.task) + '</h2><p>' + escapeHtml(summary.agent) + ' · ' + escapeHtml(durationLabel(summary.durationSeconds)) + ' · branch <code>' + escapeHtml(summary.branch) + '</code> · base <code>' + escapeHtml(summary.baseCommit) + '</code></p></div>' +
    '<div class="actions"><button class="primary" data-action="verify">Run CLI verification</button><button data-action="gate">Run CLI gate</button><button data-action="replay">Open existing replay</button></div></section>' +
    '<section class="metrics">' + metric(summary.agentChangedFileCount, "AGENT-ATTRIBUTED FILES") + metric(summary.testRuns, "TEST RUNS") + metric(summary.neverExecutedCount, "NEVER EXECUTED", summary.neverExecutedCount > 0 ? "danger" : "") + metric(summary.commandCount, "TERMINAL COMMANDS") + '</section>' +
    attribution + otherChanges + '<section class="glass evidence-panel"><div class="panel-heading"><div><span class="kicker">STORED VERIFICATION EVIDENCE</span><h2>Review source files with recorded analysis</h2></div><button class="ghost" data-action="copy-capture">Copy capture command</button></div><div class="file-list">' + rows + '</div></section>' +
    '<section class="notes"><article><h3>What the colors mean</h3><p><span class="inline-dot good"></span> verified · <span class="inline-dot warning"></span> indirectly exercised · <span class="inline-dot danger"></span> NEVER EXECUTED</p></article><article><h3>Evidence boundary</h3><p>Statuses and flags are read from this recorded manifest. The extension does not infer tests or send your code, paths, task, commands, or transcripts anywhere.</p></article></section>' +
    '</main><script nonce="' + nonce + '">const vscode=acquireVsCodeApi();document.querySelectorAll("[data-action]").forEach(function(element){element.addEventListener("click",function(){vscode.postMessage({action:element.dataset.action,path:element.dataset.path?decodeURIComponent(element.dataset.path):undefined});});});</script></body></html>';
}

function head(nonce) {
  return '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'nonce-' + nonce + '\'; script-src \'nonce-' + nonce + '\';"><style nonce="' + nonce + '">' + STYLE + "</style>";
}

function nonce() {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let value = "";
  for (let index = 0; index < 32; index += 1) {
    value += alphabet.charAt(Math.floor(Math.random() * alphabet.length));
  }
  return value;
}

async function openFile(item) {
  if (!(item instanceof EvidenceFileItem)) {
    vscode.window.showWarningMessage("Select an evidence file in the Receipts view first.");
    return;
  }
  const workspaceRoot = item.session.record.workspaceUri.fsPath;
  const sourceRoot = safeWorkspaceDirectory(workspaceRoot, item.session.record.summary.recordedCwd) || workspaceRoot;
  const target = safeRelativePath(sourceRoot, item.file.path);
  if (!target) {
    vscode.window.showWarningMessage("Receipts accepts only a relative recorded path.");
    return;
  }
  try {
    const document = await vscode.workspace.openTextDocument(vscode.Uri.file(target));
    await vscode.window.showTextDocument(document, { preview: true });
  } catch {
    vscode.window.showWarningMessage("The evidence path does not exist under the recorded workspace: " + item.file.path);
  }
}

async function openReplay(session) {
  const record = session.record;
  const replay = record.uri.with({ path: record.uri.path.replace(/\.json$/i, ".html") });
  try {
    await vscode.workspace.fs.stat(replay);
    await vscode.env.openExternal(replay);
  } catch {
    await cliTask("Receipts: Generate replay", ["replay", record.uri.fsPath], record.workspaceUri);
    vscode.window.showInformationMessage("No sibling replay exists yet. A visible Receipts task was started to generate it; open the replay again after it succeeds.");
  }
}

function openWorkbench(session, provider) {
  const panel = vscode.window.createWebviewPanel("receipts.workbench", "Receipts: " + session.record.summary.task, vscode.ViewColumn.Active, { enableScripts: true, retainContextWhenHidden: true });
  panel.webview.html = htmlFor(session.record.summary, nonce());
  panel.webview.onDidReceiveMessage(async (message) => {
    const record = session.record;
    if (message.action === "verify") {
      await cliTask("Receipts: Verify receipt", ["verify", record.uri.fsPath], record.workspaceUri);
    } else if (message.action === "gate") {
      await cliTask("Receipts: Evidence gate", ["gate", record.uri.fsPath, "--sensitive-only"], record.workspaceUri);
    } else if (message.action === "replay") {
      await openReplay(session);
    } else if (message.action === "copy-capture") {
      const task = record.summary.task === "Task not recorded" ? "" : " --task " + shellQuote(record.summary.task);
      await vscode.env.clipboard.writeText("receipts run" + task + " -- <agent command>");
      vscode.window.showInformationMessage("Receipts capture command copied to the clipboard.");
    } else if (message.action === "open-file") {
      const file = record.summary.files.find((entry) => entry.path === message.path);
      if (file) {
        await openFile(new EvidenceFileItem(session, file));
      }
    }
    provider.refresh();
  });
}

function activate(context) {
  const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBar.command = "receipts.openWorkbench";
  const provider = new ReceiptsProvider(statusBar);
  const view = vscode.window.createTreeView("receipts.sessions", { treeDataProvider: provider, showCollapseAll: true });

  async function workbench(argument) {
    const session = await resolveSession(provider, argument);
    if (!session) {
      vscode.window.showInformationMessage("No local receipt exists yet. Run receipts demo --live, then refresh Receipts.");
      return;
    }
    openWorkbench(session, provider);
  }

  context.subscriptions.push(
    statusBar,
    view,
    vscode.commands.registerCommand("receipts.refresh", () => provider.refresh()),
    vscode.commands.registerCommand("receipts.openWorkbench", workbench),
    vscode.commands.registerCommand("receipts.verify", async (item) => {
      const session = await resolveSession(provider, item);
      if (session) await cliTask("Receipts: Verify receipt", ["verify", session.record.uri.fsPath], session.record.workspaceUri);
    }),
    vscode.commands.registerCommand("receipts.gate", async (item) => {
      const session = await resolveSession(provider, item);
      if (session) await cliTask("Receipts: Evidence gate", ["gate", session.record.uri.fsPath, "--sensitive-only"], session.record.workspaceUri);
    }),
    vscode.commands.registerCommand("receipts.openReplay", async (item) => {
      const session = await resolveSession(provider, item);
      if (session) await openReplay(session);
    }),
    vscode.commands.registerCommand("receipts.copyCaptureCommand", async () => {
      await vscode.env.clipboard.writeText('receipts run --task "describe the task" -- <agent command>');
      vscode.window.showInformationMessage("Receipts capture command copied to the clipboard.");
    }),
    vscode.commands.registerCommand("receipts.openFile", openFile)
  );

  for (const folder of vscode.workspace.workspaceFolders || []) {
    const watcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(folder, ".receipts/**/*.json"));
    watcher.onDidCreate(() => provider.refresh(), undefined, context.subscriptions);
    watcher.onDidChange(() => provider.refresh(), undefined, context.subscriptions);
    watcher.onDidDelete(() => provider.refresh(), undefined, context.subscriptions);
    context.subscriptions.push(watcher);
  }
}

function deactivate() {}

module.exports = { activate, deactivate };
