"use strict";

const path = require("path");

const STATUS = {
  verified: {
    label: "verified",
    detail: "A convention-mapped test passed after the final observed edit.",
    severity: "good"
  },
  indirectly_exercised: {
    label: "indirectly exercised",
    detail: "A test suite passed after the final observed edit, but no convention-mapped test was observed.",
    severity: "warning"
  },
  never_executed: {
    label: "NEVER EXECUTED",
    detail: "No passing test was observed after the final edit in this session.",
    severity: "danger"
  },
  unparsed: {
    label: "unparsed",
    detail: "Receipts could not confidently determine verification evidence.",
    severity: "muted"
  }
};

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function objectOrEmpty(value) {
  return isObject(value) ? value : {};
}

function arrayOrEmpty(value) {
  return Array.isArray(value) ? value : [];
}

function nonEmptyString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function nonNegativeNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function normalizeStatus(value) {
  return typeof value === "string" && Object.prototype.hasOwnProperty.call(STATUS, value)
    ? value
    : "unparsed";
}

function statusInfo(value) {
  return STATUS[normalizeStatus(value)];
}

function durationLabel(seconds) {
  const value = nonNegativeNumber(seconds);
  if (value === null) {
    return "Not recorded";
  }
  const wholeSeconds = Math.floor(value);
  const minutes = Math.floor(wholeSeconds / 60);
  const remainder = wholeSeconds % 60;
  if (minutes > 0) {
    return remainder > 0 ? `${minutes}m ${remainder}s` : `${minutes}m`;
  }
  return `${remainder}s`;
}

function filePathFrom(value) {
  return isObject(value) ? nonEmptyString(value.path) : null;
}

function agentChangedFiles(manifest) {
  const final = objectOrEmpty(manifest.final);
  const candidates = Object.prototype.hasOwnProperty.call(final, "agent_changed_files")
    ? arrayOrEmpty(final.agent_changed_files)
    : arrayOrEmpty(final.changed_files);
  return candidates
    .map((entry) => ({ raw: entry, path: filePathFrom(entry) }))
    .filter((entry) => entry.path);
}

function verificationEntries(manifest) {
  const analysis = objectOrEmpty(manifest.analysis);
  return arrayOrEmpty(analysis.verification)
    .map((entry) => {
      const item = objectOrEmpty(entry);
      const filePath = filePathFrom(item);
      return filePath ? {
        path: filePath,
        status: normalizeStatus(item.status),
        command: nonEmptyString(item.test_command),
        timestamp: nonEmptyString(item.test_timestamp),
        preexistingAtStart: item.preexisting_at_start === true
      } : null;
    })
    .filter(Boolean);
}

function flaggedPaths(entries) {
  return new Set(arrayOrEmpty(entries).map(filePathFrom).filter(Boolean));
}

function reasonsByPath(entries) {
  const output = new Map();
  for (const entry of arrayOrEmpty(entries)) {
    const item = objectOrEmpty(entry);
    const filePath = filePathFrom(item);
    const reason = nonEmptyString(item.reason);
    if (filePath && reason) {
      output.set(filePath, reason);
    }
  }
  return output;
}

function changedFileDetails(manifest) {
  const changed = agentChangedFiles(manifest);
  const verified = verificationEntries(manifest);
  const changedByPath = new Map(changed.map((entry) => [entry.path, entry]));
  const analysis = objectOrEmpty(manifest.analysis);
  const scopeDrift = flaggedPaths(analysis.scope_drift);
  const riskHints = flaggedPaths(analysis.risk_hints);
  const scopeReasons = reasonsByPath(analysis.scope_drift);
  const riskReasons = reasonsByPath(analysis.risk_hints);
  return verified
    .filter((evidence) => changedByPath.has(evidence.path))
    .sort((left, right) => left.path.localeCompare(right.path))
    .map((evidence) => {
    const filePath = evidence.path;
    const match = changedByPath.get(filePath);
    const raw = match && isObject(match.raw) ? match.raw : {};
    return {
      path: filePath,
      additions: nonNegativeNumber(raw.additions),
      deletions: nonNegativeNumber(raw.deletions),
      status: evidence.status,
      command: evidence.command,
      timestamp: evidence.timestamp,
      scopeDrift: scopeDrift.has(filePath),
      sensitive: riskHints.has(filePath),
      scopeReason: scopeReasons.get(filePath) || null,
      riskReason: riskReasons.get(filePath) || null,
      preexistingAtStart: raw.preexisting_at_start === true || evidence.preexistingAtStart
    };
  });
}

function firstText(values, fallback) {
  for (const value of values) {
    const text = nonEmptyString(value);
    if (text) {
      return text;
    }
  }
  return fallback;
}

function firstNumber(values) {
  for (const value of values) {
    const number = nonNegativeNumber(value);
    if (number !== null) {
      return number;
    }
  }
  return null;
}

function summaryFromManifest(manifest, manifestPath) {
  if (!isObject(manifest)) {
    return {
      valid: false,
      error: "The receipt root is not a JSON object.",
      manifestPath: manifestPath || null
    };
  }
  if (manifest.format === "receipts-public-feed/v1") {
    return {
      valid: false,
      error: "This is an alias-only public feed, not a local full receipt manifest.",
      manifestPath: manifestPath || null,
      manifestName: manifestPath ? path.basename(manifestPath) : "receipt.json"
    };
  }
  if (
    manifest.schema_version !== 1 ||
    !isObject(manifest.meta) ||
    !isObject(manifest.timeline) ||
    !isObject(manifest.final) ||
    !Array.isArray(manifest.timeline.git_snapshots) ||
    !Array.isArray(manifest.timeline.file_changes) ||
    !Array.isArray(manifest.timeline.test_executions) ||
    !Array.isArray(manifest.timeline.notable_commands)
  ) {
    return {
      valid: false,
      error: "Unsupported receipt schema. Expected a full Receipts schema_version 1 manifest.",
      manifestPath: manifestPath || null,
      manifestName: manifestPath ? path.basename(manifestPath) : "receipt.json"
    };
  }
  const meta = objectOrEmpty(manifest.meta);
  const timeline = objectOrEmpty(manifest.timeline);
  const final = objectOrEmpty(manifest.final);
  const integrity = objectOrEmpty(manifest.integrity);
  const files = changedFileDetails(manifest);
  const testRuns = arrayOrEmpty(timeline.test_executions);
  const agentFiles = agentChangedFiles(manifest);
  const neverExecuted = files.filter((file) => file.status === "never_executed");
  const preexisting = arrayOrEmpty(meta.preexisting_dirty_paths);

  return {
    valid: true,
    manifestPath: manifestPath || null,
    manifestName: manifestPath ? path.basename(manifestPath) : "session.json",
    sessionId: firstText([meta.session_id], manifestPath ? path.basename(manifestPath, ".json") : "Not recorded"),
    task: firstText([meta.task], "Task not recorded"),
    agent: firstText([meta.agent], "unknown"),
    durationSeconds: firstNumber([meta.duration_seconds]),
    branch: firstText([meta.git_branch], "Not recorded"),
    baseCommit: firstText([meta.base_commit], "Not recorded"),
    recordedCwd: firstText([meta.cwd], null),
    commandCount: firstNumber([timeline.command_count]),
    testRuns: testRuns.length,
    files,
    agentChangedFileCount: agentFiles.length,
    otherAgentChangedCount: Math.max(0, agentFiles.length - files.length),
    neverExecutedCount: neverExecuted.length,
    scopeDriftCount: files.filter((file) => file.scopeDrift).length,
    sensitiveCount: files.filter((file) => file.sensitive).length,
    preexistingDirtyCount: firstNumber([final.preexisting_dirty_count, preexisting.length]),
    preexistingChangesRemovedCount: arrayOrEmpty(final.preexisting_changes_removed).length,
    integrityHash: firstText([integrity.sha256, integrity.manifest_sha256], null),
    signaturePresent: Boolean(nonEmptyString(integrity.signature) || nonEmptyString(integrity.ed25519_signature)),
    sourceSchema: String(manifest.schema_version)
  };
}

function treeDescription(summary) {
  if (!summary.valid) {
    return "Malformed receipt";
  }
  const pieces = [];
  if (summary.neverExecutedCount > 0) {
    pieces.push(`${summary.neverExecutedCount} NEVER EXECUTED`);
  }
  if (summary.testRuns !== null) {
    pieces.push(`${summary.testRuns} test run${summary.testRuns === 1 ? "" : "s"}`);
  }
  return pieces.length ? pieces.join(" • ") : "No analysis recorded";
}

function safeRelativePath(workspaceRoot, filePath) {
  if (!workspaceRoot || !filePath || path.isAbsolute(filePath)) {
    return null;
  }
  const target = path.resolve(workspaceRoot, filePath);
  const relative = path.relative(workspaceRoot, target);
  if (!relative || relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    return null;
  }
  return target;
}

function safeWorkspaceDirectory(workspaceRoot, recordedDirectory) {
  if (!workspaceRoot || !recordedDirectory || !path.isAbsolute(recordedDirectory)) {
    return null;
  }
  const root = path.resolve(workspaceRoot);
  const target = path.resolve(recordedDirectory);
  const relative = path.relative(root, target);
  if (relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative))) {
    return target;
  }
  return null;
}

module.exports = {
  STATUS,
  normalizeStatus,
  statusInfo,
  durationLabel,
  changedFileDetails,
  summaryFromManifest,
  treeDescription,
  safeRelativePath,
  safeWorkspaceDirectory,
  isObject
};
