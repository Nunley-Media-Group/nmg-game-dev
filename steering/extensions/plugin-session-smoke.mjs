// Plugin session smoke for nmg-game-dev. It loads this checkout as a Claude Code plugin
// (`claude --plugin-dir <checkout>`) in a fresh session inside an ephemeral test project, in its
// own Herdr tab. Once that session is ready, it asks `claude --plugin-dir <checkout> mcp list` in the
// same project for the health of every plugin MCP server, and passes once every expected server reports
// connected. `mcp list` prints one unwrapped line per server, so the result does not depend on the Herdr
// pane being tall or wide enough for the `/mcp` dialog to show the plugin servers without folding or
// truncating them. The tab and the project are removed afterwards. Only Node built-ins are imported, so the
// steering writer can load this module from its staged copy.
import { spawn } from "node:child_process";
import { mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const PLUGIN = "nmg-game-dev";
const START_TIMEOUT_MS = 180000;
const POLL_MS = 2000;
const MCP_LIST_TIMEOUT_MS = 180000;
const MCP_LIST_ATTEMPTS = 3;
const TRUST_DIALOG = /Do you trust the files in this folder\?|Yes, I trust this folder|Quick safety check/i;
const TRUST_ACCEPT_KEYS = Object.freeze(["down", "enter"]);
const SERVER_FAILED = /✘|\bfailed\b|disconnected|needs authentication/i;
const SERVER_CONNECTED = /✔|✓|\bconnected\b/i;

function bounded(value, size = 8000) {
  const text = String(value ?? "");
  return text.length <= size ? text : `${text.slice(0, size)}\n[truncated]`;
}

function run(program, args, { cwd, signal, timeoutMs } = {}) {
  return new Promise((done) => {
    if (signal?.aborted) return done({ status: null, stdout: "", stderr: "cancelled" });
    let stdout = "";
    let stderr = "";
    let child;
    let timer = null;
    const cancel = () => child?.kill("SIGTERM");
    try {
      child = spawn(program, args, { cwd, env: process.env, shell: false, stdio: ["ignore", "pipe", "pipe"] });
    } catch (error) {
      return done({ status: null, stdout, stderr: error.message });
    }
    signal?.addEventListener("abort", cancel, { once: true });
    if (timeoutMs) timer = setTimeout(() => { stderr += `\ntimed out after ${timeoutMs} ms`; cancel(); }, timeoutMs);
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", (error) => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", cancel);
      done({ status: null, stdout, stderr: error.message });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
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

// `claude mcp list` prints `plugin:<plugin>:<server>: <command or url> - <status>` per server.
function serverStatus(listing, server) {
  const prefix = `plugin:${PLUGIN}:${server}:`;
  const line = String(listing ?? "").split("\n").map((text) => text.trim()).find((text) => text.startsWith(prefix));
  if (!line) return "missing";
  const status = line.slice(line.lastIndexOf(" - ") + 3);
  if (SERVER_FAILED.test(status)) return "failed";
  return SERVER_CONNECTED.test(status) ? "connected" : "pending";
}

async function smoke(request) {
  const { projectRoot, config, identity, signal } = request;
  const expected = Array.isArray(config?.expectConnected) ? config.expectConnected : [];
  const evidence = [];
  const finish = (status, summary) => ({ schemaVersion: 1, status, summary, identity, evidence });
  if (!expected.length) return finish("incomplete", "config.expectConnected names no MCP servers");

  const project = realpathSync(mkdtempSync(join(tmpdir(), `${PLUGIN}-smoke-`)));
  const label = `${PLUGIN}-smoke-${Date.now()}`;
  // --plugin-dir already wins over a same-named installed copy; the session-only setting also
  // turns off the nmg-plugins install so the result never depends on what is installed.
  const sessionSettings = JSON.stringify({ enabledPlugins: { "nmg-game-dev@nmg-plugins": false } });
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
      "--", "--plugin-dir", projectRoot, "--settings", sessionSettings,
    ], { signal }).then((output) => { started = output; });
    let trusted = false;
    const acceptTrust = async () => {
      const screen = await run("herdr", ["pane", "read", pane, "--source", "visible", "--format", "text"], { signal });
      if (!TRUST_DIALOG.test(String(screen.stdout).replace(/\s+/g, " "))) return false;
      trusted = true;
      evidence.push(commandEvidence(`herdr pane send-keys ${pane} ${TRUST_ACCEPT_KEYS.join(" ")} (trust ephemeral project)`,
        await run("herdr", ["pane", "send-keys", pane, ...TRUST_ACCEPT_KEYS], { signal })));
      return true;
    };
    while (started === null) {
      if (signal?.aborted) return finish("incomplete", "plugin session smoke cancelled");
      await sleep(POLL_MS);
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

    const mcpListArgs = ["--plugin-dir", projectRoot, "--settings", sessionSettings, "mcp", "list"];
    let statuses = {};
    for (let attempt = 1; attempt <= MCP_LIST_ATTEMPTS; attempt += 1) {
      if (signal?.aborted) return finish("incomplete", "plugin session smoke cancelled");
      const listing = await run("claude", mcpListArgs, { cwd: project, signal, timeoutMs: MCP_LIST_TIMEOUT_MS });
      evidence.push(commandEvidence(`claude --plugin-dir ${projectRoot} mcp list (attempt ${attempt})`, listing));
      statuses = Object.fromEntries(expected.map((server) => [server, serverStatus(listing.stdout, server)]));
      if (Object.values(statuses).every((status) => status === "connected")) break;
      await sleep(POLL_MS);
    }
    const summary = expected.map((server) => `${PLUGIN}:${server} ${statuses[server]}`).join(", ");
    return Object.values(statuses).every((status) => status === "connected")
      ? finish("passed", `plugin loaded via --plugin-dir; ${summary}`)
      : finish("failed", `plugin MCP servers not all connected: ${summary}`);
  } finally {
    if (tabId) evidence.push(commandEvidence(`herdr tab close ${tabId}`, await run("herdr", ["tab", "close", tabId])));
    rmSync(project, { recursive: true, force: true });
  }
}

export const extension = Object.freeze({
  schemaVersion: 1,
  id: "project.plugin-session-smoke",
  providers: Object.freeze({
    "project.plugin-session-smoke": smoke,
  }),
});
