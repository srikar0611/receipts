(() => {
  "use strict";

  const LIVE_RECEIPT_URL = "live/latest.json";
  const FALLBACK_RECEIPT_URL = "sample-session.json";
  const $ = (id) => document.getElementById(id);
  const statuses = {
    verified: "verified",
    indirectly_exercised: "indirect coverage",
    never_executed: "NEVER EXECUTED",
    unparsed: "unparsed",
  };

  const canonicalize = (value) => {
    if (Array.isArray(value)) return value.map(canonicalize);
    if (value && typeof value === "object") {
      return Object.keys(value).sort().reduce((out, key) => {
        out[key] = canonicalize(value[key]);
        return out;
      }, {});
    }
    return value;
  };

  const canonicalBody = (receipt) => {
    const body = { ...receipt };
    delete body.integrity;
    return JSON.stringify(canonicalize(body));
  };

  async function browserHash(receipt) {
    if (!globalThis.crypto?.subtle) throw new Error("Web Crypto is unavailable");
    const bytes = new TextEncoder().encode(canonicalBody(receipt));
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  function projectionIsWellFormed(receipt) {
    return Boolean(
      receipt
      && receipt.format === "receipts-public-feed/v1"
      && receipt.public_schema_version === 1
      && receipt.receipt?.path_mode === "aliased"
      && Array.isArray(receipt.files)
      && Array.isArray(receipt.tests)
      && typeof receipt.integrity?.sha256 === "string",
    );
  }

  async function loadProjection(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const receipt = await response.json();
    if (!projectionIsWellFormed(receipt)) throw new Error("not a valid public Receipts projection");
    const actual = await browserHash(receipt);
    if (actual !== receipt.integrity.sha256) throw new Error("public projection sha256 mismatch");
    return receipt;
  }

  const ms = (value) => value === null || value === undefined ? "unparsed" : `+${(Number(value) / 1000).toFixed(1)}s`;
  const shortHash = (hash = "") => hash ? `${hash.slice(0, 4)}…${hash.slice(-4)}` : "unavailable";
  const statusLabel = (status) => statuses[status] || "unparsed";
  const gap = (receipt) => (receipt.files || []).find((file) => file.verification === "never_executed");
  const latestPassingTest = (receipt) => [...(receipt.tests || [])]
    .filter((test) => test.result === "passed" && Number.isInteger(test.offset_ms))
    .sort((left, right) => left.offset_ms - right.offset_ms)
    .at(-1);

  function setText(id, value) {
    const element = $(id);
    if (element) element.textContent = value;
  }

  function setReplayLinks(live) {
    const url = live ? "live/latest.html#red-flag" : "replay.html#red-flag";
    for (const id of ["forensicLink", "primaryReplayLink", "workbenchLink", "consoleReplayLink", "footerReplayLink"]) {
      const element = $(id);
      if (element) element.href = url;
    }
  }

  function renderVerification(receipt) {
    const holder = $("verificationList");
    if (!holder) return;
    holder.replaceChildren();
    for (const file of receipt.files || []) {
      const row = document.createElement("div");
      row.className = `verification-row ${file.verification || "unparsed"}`;
      const dot = document.createElement("span");
      dot.className = "verification-dot";
      const name = document.createElement("code");
      name.textContent = file.id;
      const label = document.createElement("small");
      label.textContent = statusLabel(file.verification);
      row.append(dot, name, label);
      holder.append(row);
    }
  }

  function renderEvents(receipt) {
    const holder = $("eventFeed");
    if (!holder) return;
    holder.replaceChildren();
    const events = [
      ...(receipt.files || []).map((file) => ({
        kind: "file",
        offset: file.last_modified_offset_ms,
        title: file.id,
        detail: statusLabel(file.verification),
        alert: file.verification === "never_executed",
      })),
      ...(receipt.tests || []).map((test) => ({
        kind: "test",
        offset: test.offset_ms,
        title: `${test.runner} test run`,
        detail: test.result || "unparsed",
        alert: test.result === "failed",
      })),
    ].sort((left, right) => (left.offset ?? Number.MAX_SAFE_INTEGER) - (right.offset ?? Number.MAX_SAFE_INTEGER));
    for (const event of events) {
      const card = document.createElement("div");
      card.className = `event-card ${event.kind}${event.alert ? " alert" : ""}`;
      const time = document.createElement("time");
      time.textContent = ms(event.offset);
      const dot = document.createElement("i");
      dot.className = "event-dot";
      const body = document.createElement("div");
      const title = document.createElement("b");
      const detail = document.createElement("span");
      title.textContent = event.title;
      detail.textContent = event.detail;
      body.append(title, detail);
      card.append(time, dot, body);
      holder.append(card);
    }
  }

  function render(receipt, live, fallbackReason = "") {
    const summary = receipt.summary || {};
    const publication = receipt.publication || {};
    const red = gap(receipt);
    const lastPass = latestPassingTest(receipt);
    const mode = live ? "LIVE PUBLISHED" : "CURATED SAMPLE";
    const publicationLabel = live ? "Receipt / latest public feed" : "Receipt / safe fallback sample";
    const source = live ? "evidence://public/live/latest" : "evidence://public/sample";

    setText("evidenceMode", mode);
    setText("evidenceLabel", publicationLabel);
    setText("vaultTask", live ? "Latest GitHub Actions evidence" : "Curated recorded evidence");
    setText("vaultSession", `${receipt.receipt?.id || "public receipt"} · ${receipt.receipt?.agent || "other"} agent · ${ms(receipt.receipt?.duration_ms)}`);
    setText("fileMetric", String(summary.agent_changed_file_count || 0));
    setText("testMetric", String(summary.test_run_count || 0));
    setText("gapMetric", String(summary.never_executed_count || 0));
    setText("hashShort", shortHash(receipt.integrity?.sha256));
    setText("consoleMeta", live
      ? `Latest GitHub Actions demo receipt · ${publication.published_at || "publish time unavailable"}`
      : `Verified alias-only sample${fallbackReason ? " · live feed unavailable" : ""}`);
    setText("consoleHash", `public projection sha256 ${shortHash(receipt.integrity?.sha256)}`);
    setText("consoleSource", source);
    setText("liveStatusNote", live
      ? "A fresh, alias-only receipt was published by the trusted GitHub Actions demo workflow."
      : "Live feed unavailable. Showing the separately verified, alias-only recorded sample.");
    setReplayLinks(live);

    if (red) {
      setText("redFindingPath", `${red.id} — NEVER EXECUTED`);
      setText("redFindingCopy", "No passing test was observed after this source alias’s final edit.");
      if (lastPass !== undefined && red.last_modified_offset_ms !== null && lastPass?.offset_ms !== null) {
        const gapMs = Math.max(0, red.last_modified_offset_ms - lastPass.offset_ms);
        setText("lateGap", `${(gapMs / 1000).toFixed(1)}s after final pass`);
      } else {
        setText("lateGap", "relative timing unavailable");
      }
    } else {
      setText("redFindingPath", "No NEVER EXECUTED source alias");
      setText("redFindingCopy", "This receipt has no source alias with a recorded verification gap.");
      setText("lateGap", "no red finding");
    }

    renderVerification(receipt);
    renderEvents(receipt);
    const integrity = $("landingIntegrity");
    if (integrity) {
      integrity.className = "integrity-state good";
      integrity.textContent = "browser hash verified";
    }
  }

  async function verifyLanding(receipt) {
    const button = $("verifyLanding");
    const state = $("landingIntegrity");
    if (!button || !state) return;
    button.disabled = true;
    button.textContent = "Verifying…";
    try {
      const actual = await browserHash(receipt);
      if (actual !== receipt.integrity?.sha256) throw new Error("sha256 mismatch");
      state.className = "integrity-state good";
      state.textContent = "browser hash verified";
      button.textContent = "Verified ✓";
    } catch (error) {
      state.className = "integrity-state bad";
      state.textContent = "verification failed";
      button.textContent = "Hash mismatch";
    }
    button.disabled = false;
  }

  async function boot() {
    let receipt;
    let live = true;
    let reason = "";
    try {
      receipt = await loadProjection(LIVE_RECEIPT_URL);
    } catch (error) {
      live = false;
      reason = error instanceof Error ? error.message : "unavailable";
      try {
        receipt = await loadProjection(FALLBACK_RECEIPT_URL);
      } catch (fallbackError) {
        setText("vaultTask", "Public evidence unavailable");
        setText("vaultSession", "Neither the live feed nor the safe sample passed browser verification.");
        setText("liveStatusNote", "Do not rely on this page until a verified public projection is available.");
        return;
      }
    }
    render(receipt, live, reason);
    $("verifyLanding")?.addEventListener("click", () => verifyLanding(receipt));
  }

  boot();
})();
