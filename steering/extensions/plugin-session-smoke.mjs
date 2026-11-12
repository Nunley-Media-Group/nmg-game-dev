// Plugin session smoke for nmg-game-dev. It loads this checkout as a Claude Code plugin
// (`claude --plugin-dir <checkout>`) in a fresh session inside an ephemeral test project, in its
// own Herdr tab, and passes once every expected plugin MCP server shows as connected in `/mcp`.
// The tab and the project are removed afterwards. Only Node built-ins are imported, so the
// steering writer can load this module from its staged copy.
import { spawn } from "node:child_process";
import { mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const PLUGIN = "nmg-game-dev";
const START_TIMEOUT_MS = 180000;
const POLL_MS = 2000;
const MCP_POLLS = 60;
const TRUST_DIALOG = /Do you trust the files in this folder\?|Yes, I trust this folder|Quick safety check/i;
const TRUST_ACCEPT_KEYS = Object.freeze(["down", "enter"]);
const SERVER_FAILED = /✘|\bfailed\b|disconnected|needs authentication/i;
const SERVER_CONNECTED = /✔|✓|\bconnected\b/i;
const MORE_ABOVE = /↑\s*\d+\s+more/;
const MORE_BELOW = /↓\s*\d+\s+more/;
const KEY_SETTLE_MS = 250;
const MAX_SCROLL_KEYS = 200;

function bounded(value, size = 8000) {
  const text = String(value ?? "");
  return text.length <= size ? text : `${text.slice(0, size)}\n[truncated]`;
}

function run(program, args, { cwd, signal } = {}) {
  return new Promise((done) => {
    if (signal?.aborted) return done({ status: null, stdout: "", stderr: "cancelled" });
    let stdout = "";
    let stderr = "";
    let child;
    const cancel = () => child?.kill("SIGTERM");
    try {
      child = spawn(program, args, { cwd, env: process.env, shell: false, stdio: ["ignore", "pipe", "pipe"] });
    } catch (error) {
      return done({ status: null, stdout, stderr: error.message });
    }
    signal?.addEventListener("abort", cancel, { once: true });
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", (error) => {
      signal?.removeEventListener("abort", cancel);
      done({ status: null, stdout, stderr: error.message });
    });
    child.on("close", (code) => {
      signal?.removeEventListener("abort", cancel);
      done({ status: code, stdout, stderr });
    });
  });
}

function herdrResult(output) {
  if (output?.status !== 0) return null;
  try { return JSON.parse(output.stdout).result ?? null; } catch { return null; }
}

function commandEvidence(summary, output) {
  return { kind: "command", summary, artifact: null, stdout: bounded(output?.stdout), stderr: bounded(output?.stderr, 4000) };
}

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

// `row` is the latest /mcp row that names the server, or undefined when no read has shown one.
function serverStatus(row) {
  if (row === undefined) return "missing";
  if (SERVER_FAILED.test(row)) return "failed";
  return SERVER_CONNECTED.test(row) ? "connected" : "pending";
}

const readVisible = async (pane, signal) =>
  (await run("herdr", ["pane", "read", pane, "--source", "visible", "--format", "text"], { signal })).stdout;

// Claude Code draws /mcp as a scrolling selection list, so a short tab shows a window of rows with
// `↑ N more` / `↓ N more` markers. Navigation keys only move the selection, so the pass presses up
// while the top marker shows and then down while the bottom marker shows, reading after each key.
async function pageMcpList(pane, { signal, keySettleMs, onRead }) {
  let screen = await readVisible(pane, signal);
  onRead(screen);
  for (const [marker, key] of [[MORE_ABOVE, "up"], [MORE_BELOW, "down"]]) {
    for (let presses = 0; marker.test(screen) && presses < MAX_SCROLL_KEYS; presses += 1) {
      if ((await run("herdr", ["pane", "send-keys", pane, key], { signal })).status !== 0) return;
      await sleep(keySettleMs);
      screen = await readVisible(pane, signal);
      onRead(screen);
    }
  }
}

async function smoke(request, { pollMs, keySettleMs, mcpPolls }) {
  const { projectRoot, config, identity, signal } = request;
  const expected = Array.isArray(config?.expectConnected) ? config.expectConnected : [];
  const evidence = [];
  const finish = (status, summary) => ({ schemaVersion: 1, status, summary, identity, evidence });
  if (!expected.length) return finish("incomplete", "config.expectConnected names no MCP servers");

  const project = realpathSync(mkdtempSync(join(tmpdir(), `${PLUGIN}-smoke-`)));
  const label = `${PLUGIN}-smoke-${Date.now()}`;
  let tabId = null;
  try {
    evidence.push(commandEvidence(`git init (ephemeral test project ${project})`, await run("git", ["init", "-q"], { cwd: project, signal })));
    const created = await run("herdr", ["tab", "create", "--cwd", project, "--label", label, "--no-focus"], { signal });
    evidence.push(commandEvidence("herdr tab create", created));
    tabId = (herdrResult(await run("herdr", ["tab", "list"], { signal }))?.tabs ?? []).find((tab) => tab.label === label)?.tab_id ?? null;
    if (!tabId) return finish("incomplete", "herdr tab for the plugin session was not created");
    const pane = (herdrResult(await run("herdr", ["pane", "list"], { signal }))?.panes ?? []).find((entry) => entry.tab_id === tabId)?.pane_id ?? null;
    if (!pane) return finish("incomplete", `no pane found in herdr tab ${tabId}`);

    let started = null;
    const starting = run("herdr", [
      "agent", "start", label, "--kind", "claude", "--pane", pane, "--timeout", String(START_TIMEOUT_MS),
      // --plugin-dir already wins over a same-named installed copy; the session-only setting also
      // turns off the nmg-plugins install so the result never depends on what is installed.
      "--", "--plugin-dir", projectRoot, "--settings", JSON.stringify({ enabledPlugins: { "nmg-game-dev@nmg-plugins": false } }),
    ], { signal }).then((output) => { started = output; });
    let trusted = false;
    while (started === null) {
      if (signal?.aborted) return finish("incomplete", "plugin session smoke cancelled");
      await sleep(pollMs);
      if (trusted || started !== null) continue;
      const screen = await readVisible(pane, signal);
      if (TRUST_DIALOG.test(screen.replace(/\s+/g, " "))) {
        trusted = true;
        evidence.push(commandEvidence(`herdr pane send-keys ${pane} ${TRUST_ACCEPT_KEYS.join(" ")} (trust ephemeral project)`,
          await run("herdr", ["pane", "send-keys", pane, ...TRUST_ACCEPT_KEYS], { signal })));
      }
    }
    await starting;
    evidence.push(commandEvidence(`herdr agent start ${label} -- --plugin-dir ${projectRoot}`, started));
    if (started.status !== 0) return finish("failed", "Claude Code session with --plugin-dir did not become ready");

    evidence.push(commandEvidence("herdr agent prompt /mcp", await run("herdr", ["agent", "prompt", label, "/mcp"], { signal })));
    // Every distinct line from every read, in first-seen order, and the latest row naming each server.
    const lines = new Set();
    const latest = new Map();
    const record = (screen) => {
      for (const line of screen.split("\n")) {
        if (!line.trim()) continue;
        lines.add(line);
        for (const server of expected) {
          if (line.includes(PLUGIN) && line.includes(server)) latest.set(server, line);
        }
      }
    };
    let statuses = {};
    for (let poll = 0; poll < mcpPolls; poll += 1) {
      if (signal?.aborted) return finish("incomplete", "plugin session smoke cancelled");
      await sleep(pollMs);
      await pageMcpList(pane, { signal, keySettleMs, onRead: record });
      statuses = Object.fromEntries(expected.map((server) => [server, serverStatus(latest.get(server))]));
      if (Object.values(statuses).every((status) => status === "connected" || status === "failed")) break;
    }
    evidence.push({ kind: "artifact", summary: "/mcp list rows read in the plugin session", artifact: bounded([...lines].join("\n")) });
    const summary = expected.map((server) => `${PLUGIN}:${server} ${statuses[server]}`).join(", ");
    return Object.values(statuses).every((status) => status === "connected")
      ? finish("passed", `plugin loaded via --plugin-dir; ${summary}`)
      : finish("failed", `plugin MCP servers not all connected: ${summary}`);
  } finally {
    if (tabId) evidence.push(commandEvidence(`herdr tab close ${tabId}`, await run("herdr", ["tab", "close", tabId])));
    rmSync(project, { recursive: true, force: true });
  }
}

// The factory is the testability seam: the provider is createSmoke() with the production timings.
export function createSmoke({ pollMs = POLL_MS, keySettleMs = KEY_SETTLE_MS, mcpPolls = MCP_POLLS } = {}) {
  return (request) => smoke(request, { pollMs, keySettleMs, mcpPolls });
}

export const extension = Object.freeze({
  schemaVersion: 1,
  id: "project.plugin-session-smoke",
  providers: Object.freeze({
    "project.plugin-session-smoke": createSmoke(),
  }),
});
