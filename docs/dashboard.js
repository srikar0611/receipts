(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const text = (id, value) => { const node = $(id); if (node) node.textContent = value; };
  const shortHash = (hash = "") => hash ? `${hash.slice(0, 4)}…${hash.slice(-4)}` : "unavailable";
  const duration = (seconds) => `${Number(seconds || 0).toFixed(1)}s`;
  const relativeSeconds = (timestamp, manifest) => Math.max(0, (Date.parse(timestamp) - Date.parse(manifest.meta.started_at)) / 1000);
  const relativeTime = (timestamp, manifest) => `${relativeSeconds(timestamp, manifest).toFixed(1).padStart(4, "0")}s`;
  const labelFor = (status) => ({ verified: "verified", indirectly_exercised: "indirect", never_executed: "NEVER EXECUTED" }[status] || status || "unparsed");

  function canonicalize(value) {
    if (Array.isArray(value)) return value.map(canonicalize);
    if (value && typeof value === "object") {
      return Object.keys(value).sort().reduce((copy, key) => {
        copy[key] = canonicalize(value[key]);
        return copy;
      }, {});
    }
    return value;
  }

  function canonicalBody(manifest) {
    const body = { ...manifest };
    delete body.integrity;
    return JSON.stringify(canonicalize(body));
  }

  async function browserHash(manifest) {
    if (!globalThis.crypto?.subtle) throw new Error("Web Crypto is unavailable in this browser");
    const bytes = new TextEncoder().encode(canonicalBody(manifest));
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  function element(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = content;
    return node;
  }

  function sourceEvents(manifest) {
    const changes = (manifest.timeline.file_changes || []).map((change) => ({
      timestamp: change.last_modified_observed_at,
      kind: "change",
      path: change.path,
      detail: change.path.includes("__pycache__") ? "generated Python cache observed" : "file change observed",
      alert: change.path === "src/billing/invoice.py",
    }));
    const tests = (manifest.timeline.test_executions || []).map((run) => ({
      timestamp: run.timestamp,
      kind: "test",
      path: run.command,
      detail: run.summary || run.result || "test result unparsed",
      alert: run.result === "failed",
    }));
    return [...changes, ...tests].sort((left, right) => String(left.timestamp).localeCompare(String(right.timestamp)));
  }

  function renderVerification(manifest) {
    const list = $("verificationList");
    list.replaceChildren();
    for (const item of manifest.analysis.verification || []) {
      const row = element("div", `verification-row ${item.status}`);
      row.append(element("span", "verification-dot"), element("code", "", item.path), element("small", "", labelFor(item.status)));
      list.append(row);
    }
  }

  function renderEventFeed(manifest) {
    const feed = $("eventFeed");
    feed.replaceChildren();
    const visible = sourceEvents(manifest).filter((event) => !event.path.includes("__pycache__"));
    for (const event of visible) {
      const card = element("div", `event-card ${event.kind}${event.alert ? " alert" : ""}`);
      const time = element("time", "", relativeTime(event.timestamp, manifest));
      const dot = element("span", "event-dot");
      const body = element("div");
      body.append(element("b", "", event.path), element("span", "", event.detail));
      card.append(time, dot, body);
      feed.append(card);
    }
  }

  function setIntegrityState(state, message) {
    const badge = $("landingIntegrity");
    badge.className = `integrity-state ${state}`;
    badge.textContent = message;
  }

  function render(manifest) {
    const verifications = manifest.analysis.verification || [];
    const gap = verifications.find((item) => item.status === "never_executed");
    const finalTest = [...(manifest.timeline.test_executions || [])].filter((item) => item.result === "passed").sort((a, b) => String(a.timestamp).localeCompare(String(b.timestamp))).at(-1);
    const finalBillingChange = (manifest.timeline.file_changes || []).find((item) => item.path === gap?.path);
    const gapSeconds = finalTest && finalBillingChange ? relativeSeconds(finalBillingChange.last_modified_observed_at, manifest) - relativeSeconds(finalTest.timestamp, manifest) : null;
    const expectedHash = manifest.integrity?.sha256 || "";

    text("vaultTask", manifest.meta.task || "Task was not recorded");
    text("vaultSession", `${duration(manifest.meta.duration_seconds)} · ${manifest.timeline.command_count || 0} terminal commands · ${manifest.meta.agent || "other"}`);
    text("fileMetric", String((manifest.final.changed_files || []).length));
    text("testMetric", String((manifest.timeline.test_executions || []).length));
    text("gapMetric", String(verifications.filter((item) => item.status === "never_executed").length));
    text("hashShort", shortHash(expectedHash));
    text("consoleHash", `sha256 ${shortHash(expectedHash)} · unsigned sample manifest`);
    text("consoleMeta", `${manifest.meta.session_id} · ${manifest.meta.git_branch || "no branch"} · ${manifest.timeline.command_count || 0} observed commands`);

    if (gap) {
      text("redFindingPath", gap.path);
      text("redFindingCopy", gapSeconds === null ? "No test execution was observed after its final edit." : `changed ${gapSeconds.toFixed(1)}s after the final passing test — no later test observed.`);
      text("lateGap", gapSeconds === null ? "no later test" : `${gapSeconds.toFixed(1)}s after final test`);
    }

    renderVerification(manifest);
    renderEventFeed(manifest);
    setIntegrityState("pending", "ready to verify");

    $("verifyLanding").addEventListener("click", async () => {
      const button = $("verifyLanding");
      button.disabled = true;
      button.textContent = "Verifying receipt…";
      try {
        const actualHash = await browserHash(manifest);
        if (actualHash === expectedHash) {
          setIntegrityState("good", "sha256 verified");
          button.textContent = "Receipt verified ✓";
        } else {
          setIntegrityState("bad", "hash mismatch");
          button.textContent = "Hash mismatch";
        }
      } catch (error) {
        setIntegrityState("bad", "use receipts verify");
        button.textContent = "Web Crypto unavailable";
      }
      button.disabled = false;
    }, { once: true });
  }

  async function boot() {
    try {
      const response = await fetch("sample-session.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`manifest request returned ${response.status}`);
      render(await response.json());
    } catch (error) {
      text("vaultTask", "Sample evidence could not load");
      text("vaultSession", "Serve this page through the deployed demo or run receipts demo locally.");
      text("redFindingPath", "Evidence unavailable");
      text("redFindingCopy", "The viewer never substitutes guessed data when a manifest cannot be read.");
      text("consoleMeta", "The manifest did not load; no evidence was fabricated.");
      setIntegrityState("bad", "manifest unavailable");
    }
  }

  boot();
})();
