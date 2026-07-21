"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const {
  changedFileDetails,
  normalizeStatus,
  safeRelativePath,
  safeWorkspaceDirectory,
  summaryFromManifest,
  treeDescription
} = require("../lib/receipt-model");

function fullManifest() {
  return {
    schema_version: 1,
    meta: {
      session_id: "session-example",
      duration_seconds: 12.4,
      agent: "other",
      task: "fix the login bug",
      git_branch: "master",
      base_commit: "abc1234",
      cwd: "/repo/.receipts/live-proofs/live-proof-example",
      preexisting_dirty_paths: ["src/billing/already_dirty.py"]
    },
    timeline: {
      command_count: 11,
      git_snapshots: [],
      file_changes: [],
      notable_commands: [],
      test_executions: [
        { timestamp: "2026-07-21T17:00:00.000Z", command: "python -m unittest -q tests/test_login.py", result: "passed", summary: "OK" },
        { timestamp: "2026-07-21T17:00:03.000Z", command: "python -m unittest -q tests/test_login.py", result: "passed", summary: "OK" }
      ]
    },
    final: {
      changed_files: [
        { path: "src/billing/already_dirty.py", additions: 1, deletions: 0 }
      ],
      agent_changed_files: [
        { path: "src/auth/login.py", additions: 12, deletions: 2, preexisting_at_start: false },
        { path: "src/auth/session.py", additions: 4, deletions: 0, preexisting_at_start: false },
        { path: "src/billing/invoice.py", additions: 9, deletions: 0, preexisting_at_start: false }
      ]
    },
    analysis: {
      verification: [
        { path: "src/auth/login.py", status: "verified", test_command: "python -m unittest -q tests/test_login.py", test_timestamp: "2026-07-21T17:00:03.000Z" },
        { path: "src/auth/session.py", status: "indirectly_exercised", test_command: "python -m unittest -q tests/test_login.py", test_timestamp: "2026-07-21T17:00:03.000Z" },
        { path: "src/billing/invoice.py", status: "never_executed", test_command: null, test_timestamp: null }
      ],
      scope_drift: [{ path: "src/billing/invoice.py", reason: "No task token match (heuristic)." }],
      risk_hints: [{ path: "src/auth/login.py", reason: "sensitive auth path" }, { path: "src/billing/invoice.py", reason: "sensitive billing path" }]
    },
    integrity: {
      sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  };
}

test("summarizes exact stored verification evidence from agent-attributed files", () => {
  const summary = summaryFromManifest(fullManifest(), "/repo/.receipts/session-example.json");

  assert.equal(summary.valid, true);
  assert.equal(summary.task, "fix the login bug");
  assert.equal(summary.agent, "other");
  assert.equal(summary.commandCount, 11);
  assert.equal(summary.testRuns, 2);
  assert.equal(summary.files.length, 3);
  assert.equal(summary.neverExecutedCount, 1);
  assert.equal(summary.preexistingDirtyCount, 1);
  assert.equal(summary.recordedCwd, "/repo/.receipts/live-proofs/live-proof-example");
  assert.equal(summary.files.find((file) => file.path === "src/auth/login.py").status, "verified");
  assert.equal(summary.files.find((file) => file.path === "src/auth/login.py").command, "python -m unittest -q tests/test_login.py");
  assert.equal(summary.files.find((file) => file.path === "src/billing/invoice.py").scopeDrift, true);
  assert.equal(summary.files.find((file) => file.path === "src/billing/invoice.py").sensitive, true);
  assert.equal(treeDescription(summary), "1 NEVER EXECUTED • 2 test runs");
});

test("honors an explicitly empty agent_changed_files list as zero agent work", () => {
  const manifest = fullManifest();
  manifest.final.agent_changed_files = [];

  const files = changedFileDetails(manifest);

  assert.equal(files.length, 0);
  assert.equal(files.some((file) => file.path === "src/billing/already_dirty.py"), false);
});

test("does not invent a verification row when the manifest stored no analysis entry", () => {
  const manifest = {
    schema_version: 1,
    meta: {},
    timeline: { git_snapshots: [], file_changes: [], test_executions: [], notable_commands: [] },
    final: { agent_changed_files: [{ path: "src/new_file.py", additions: null, deletions: null }] },
    analysis: {},
    integrity: {}
  };

  const summary = summaryFromManifest(manifest, "/repo/.receipts/session-minimal.json");

  assert.equal(summary.task, "Task not recorded");
  assert.equal(summary.agent, "unknown");
  assert.equal(summary.testRuns, 0);
  assert.equal(summary.files.length, 0);
  assert.equal(summary.otherAgentChangedCount, 1);
});

test("normalizes only known statuses", () => {
  assert.equal(normalizeStatus("verified"), "verified");
  assert.equal(normalizeStatus("indirectly_exercised"), "indirectly_exercised");
  assert.equal(normalizeStatus("never_executed"), "never_executed");
  assert.equal(normalizeStatus("indirectly exercised"), "unparsed");
  assert.equal(normalizeStatus("probably fine"), "unparsed");
});

test("rejects the public alias-only projection as a local full receipt", () => {
  const summary = summaryFromManifest({ format: "receipts-public-feed/v1", receipt: {}, files: [] }, "/repo/docs/sample-session.json");

  assert.equal(summary.valid, false);
  assert.match(summary.error, /alias-only public feed/);
});

test("uses the same duration truncation as the Receipts Trust Card", () => {
  const summary = summaryFromManifest(fullManifest(), "/repo/.receipts/session-example.json");
  summary.durationSeconds = 12.773;

  const { durationLabel } = require("../lib/receipt-model");
  assert.equal(durationLabel(summary.durationSeconds), "12s");
});

test("does not allow a receipt path to escape the workspace", () => {
  const root = path.resolve("/repo");

  assert.equal(safeRelativePath(root, "src/auth/login.py"), path.join(root, "src", "auth", "login.py"));
  assert.equal(safeRelativePath(root, "../secrets.txt"), null);
  assert.equal(safeRelativePath(root, "/etc/passwd"), null);
});

test("opens recorded source only when its workspace is contained by the opened workspace", () => {
  const root = path.resolve("/repo");

  assert.equal(
    safeWorkspaceDirectory(root, "/repo/.receipts/live-proofs/live-proof-example"),
    path.join(root, ".receipts", "live-proofs", "live-proof-example")
  );
  assert.equal(safeWorkspaceDirectory(root, "/other-repo"), null);
  assert.equal(safeWorkspaceDirectory(root, "relative-repo"), null);
});
