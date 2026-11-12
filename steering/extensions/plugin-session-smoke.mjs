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
const PLUGIN_PREFIX = `plugin:${PLUGIN}:`;
const SERVER_COUNT = /\b(\d+)\s+servers?\b/;

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
// `press(key)` sends one key, waits for the screen to settle, and returns false when Herdr refused it.
async function pageMcpList(pane, { signal, press, onRead }) {
  let screen = await readVisible(pane, signal);
  onRead(screen);
  for (const [marker, key] of [[MORE_ABOVE, "up"], [MORE_BELOW, "down"]]) {
    for (let presses = 0; marker.test(screen) && presses < MAX_SCROLL_KEYS; presses += 1) {
      if (!(await press(key))) return;
      screen = await readVisible(pane, signal);
      onRead(screen);
    }
  }
}

// A narrow pane truncates long /mcp names ("✔ plugin:nmg-game…   9 tools"), so the row no longer
// names its server. A row is worth opening when its cut-off name could be one of this plugin's.
function truncatedPluginRow(line) {
  const name = /(\S+)…/.exec(line ?? "")?.[1];
  return name !== undefined && name.length >= "plugin:".length
    && (PLUGIN_PREFIX.startsWith(name) || name.startsWith(PLUGIN_PREFIX));
}

const selectedRow = (screen) => screen.split("\n").find((line) => line.includes("❯"));

// The detail view names the server in full above its "Status:" line, wrapped to the pane width
// ("Plugin:nmg-game-dev:blender MCP" / "Server"). Returns one row holding the name and the status,
// or null when the screen is not a detail view. Lines are joined without spaces so that a name
// hard-broken across lines reads whole again.
function detailRow(screen) {
  const lines = screen.split("\n");
  const status = lines.findIndex((line) => /^\s*Status:/.test(line));
  if (status < 0) return null;
  const start = lines.slice(0, status).findLastIndex((line) => /^\s*plugin:/i.test(line));
  if (start < 0) return null;
  return `${lines.slice(start, status).map((line) => line.trim()).join("")} ${lines[status].trim()}`;
}

// Opens the detail view of every selected row whose name is truncated. Enter opens the detail, and
// esc returns to the list with its first row selected, so after the first inspection the walk
// knows its position and returns to it. The list wraps, so `count` down presses visit every row.
async function inspectTruncatedRows(pane, { signal, press, count, onRead, done }) {
  let position = null; // rows below the first row, known once an inspection has reset the list
  for (let step = 0; step <= 2 * count && !done(); step += 1) {
    const screen = await readVisible(pane, signal);
    onRead(screen);
    if (truncatedPluginRow(selectedRow(screen))) {
      if (!(await press("enter"))) return;
      const row = detailRow(await readVisible(pane, signal));
      if (row === null) return;
      onRead(row);
      if (!(await press("esc"))) return;
      if (position === null) {
        position = 0;
        continue;
      }
      for (let back = 0; back < position; back += 1) if (!(await press("down"))) return;
    }
    if (position !== null && position >= count - 1) return;
    if (!(await press("down"))) return;
    if (position !== null) position += 1;
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
    const acceptTrust = async () => {
      const screen = await readVisible(pane, signal);
      if (!TRUST_DIALOG.test(String(screen ?? "").replace(/\s+/g, " "))) return false;
      trusted = true;
      evidence.push(commandEvidence(`herdr pane send-keys ${pane} ${TRUST_ACCEPT_KEYS.join(" ")} (trust ephemeral project)`,
        await run("herdr", ["pane", "send-keys", pane, ...TRUST_ACCEPT_KEYS], { signal })));
      return true;
    };
    while (started === null) {
      if (signal?.aborted) return finish("incomplete", "plugin session smoke cancelled");
      await sleep(pollMs);
      if (!trusted && started === null) await acceptTrust();
    }
    await starting;
    evidence.push(commandEvidence(`herdr agent start ${label} -- --plugin-dir ${projectRoot}`, started));
    // `agent start` can report the session blocked on the trust dialog before the first poll sees it.
    if (started.status !== 0 && !trusted && await acceptTrust()) {
      started = await run("herdr", ["agent", "wait", label, "--until", "idle", "--timeout", String(START_TIMEOUT_MS)], { signal });
      evidence.push(commandEvidence(`herdr agent wait ${label} --until idle (after trusting the project)`, started));
    }
    if (started.status !== 0) return finish("failed", "Claude Code session with --plugin-dir did not become ready");

    evidence.push(commandEvidence("herdr agent prompt /mcp", await run("herdr", ["agent", "prompt", label, "/mcp"], { signal })));
    // Every distinct line from every read, in first-seen order, and the latest row naming each server.
    const lines = new Set();
    const latest = new Map();
    // Truncated rows seen in the current poll (selection mark removed), and the /mcp server count.
    let truncated = new Set();
    let serverCount = MAX_SCROLL_KEYS;
    const record = (screen) => {
      for (const line of screen.split("\n")) {
        if (!line.trim()) continue;
        lines.add(line);
        if (truncatedPluginRow(line)) truncated.add(line.replace("❯", " ").trim());
        const count = SERVER_COUNT.exec(line);
        if (count) serverCount = Number(count[1]);
        for (const server of expected) {
          if (line.includes(PLUGIN) && line.includes(server)) latest.set(server, line);
        }
      }
    };
    // A refused key ends the current pass early; the evidence says so, since the rows not reached
    // would otherwise only show up as `missing`.
    const press = async (key) => {
      const output = await run("herdr", ["pane", "send-keys", pane, key], { signal });
      if (output.status !== 0) {
        evidence.push(commandEvidence(`herdr pane send-keys ${pane} ${key} failed; /mcp paging stopped early`, output));
        return false;
      }
      await sleep(keySettleMs);
      return true;
    };
    const settled = (server) => ["connected", "failed"].includes(serverStatus(latest.get(server)));
    let statuses = {};
    let inspected = null; // the truncated rows the last detail walk ran for
    for (let poll = 0; poll < mcpPolls; poll += 1) {
      if (signal?.aborted) return finish("incomplete", "plugin session smoke cancelled");
      await sleep(pollMs);
      truncated = new Set();
      await pageMcpList(pane, { signal, press, onRead: record });
      // Walk the detail views only when an expected server is unresolved and the truncated rows
      // changed since the last walk, so a genuinely missing server does not repeat it every poll.
      const key = [...truncated].sort().join("\n");
      if (truncated.size && key !== inspected && !expected.every(settled)) {
        inspected = key;
        await inspectTruncatedRows(pane, {
          signal, press, count: serverCount, onRead: record, done: () => expected.every(settled),
        });
      }
      statuses = Object.fromEntries(expected.map((server) => [server, serverStatus(latest.get(server))]));
      if (expected.every(settled)) break;
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
