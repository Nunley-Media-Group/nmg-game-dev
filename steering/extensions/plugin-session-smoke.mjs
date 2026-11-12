// Plugin session smoke for nmg-game-dev. It loads this checkout as a Claude Code plugin
// (`claude --plugin-dir <checkout>`) in a fresh headless session inside an ephemeral test project
// and passes once every expected plugin MCP server reports `connected`. The session runs with
// stream-json input and output, and the smoke asks for server status with `mcp_status` control
// requests. It never sends a prompt, so no model call is made, and a headless session shows no
// folder-trust dialog and no terminal UI whose width could truncate server names. The session and
// the project are removed afterwards. Only Node built-ins are imported, so the steering writer can
// load this module from its staged copy.
import { spawn } from "node:child_process";
import { mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const PLUGIN = "nmg-game-dev";
const STATUS_TIMEOUT_MS = 180000;
const REQUEST_TIMEOUT_MS = 30000;
const POLL_MS = 2000;
// Servers are registered as soon as the session starts, so a missing server will not appear later.
const TERMINAL = new Set(["connected", "failed", "needs-auth", "disabled", "missing"]);

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

function commandEvidence(summary, output) {
  return { kind: "command", summary, artifact: null, stdout: bounded(output?.stdout), stderr: bounded(output?.stderr, 4000) };
}

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

// A headless Claude Code session driven over stream-json. `request` sends one control request and
// resolves with its response payload, or null when the session ends or the request times out.
function startSession(args, { cwd }) {
  const pending = new Map();
  const session = { stderr: "", exited: false, exitCode: null, spawnError: null };
  let buffer = "";
  let next = 0;
  const settle = (id, value) => {
    const entry = pending.get(id);
    if (!entry) return;
    pending.delete(id);
    clearTimeout(entry.timer);
    entry.done(value);
  };
  const child = spawn("claude", args, { cwd, env: process.env, shell: false, stdio: ["pipe", "pipe", "pipe"] });
  child.on("error", (error) => {
    session.spawnError = error.message;
    session.exited = true;
    for (const id of [...pending.keys()]) settle(id, null);
  });
  child.on("close", (code) => {
    session.exited = true;
    session.exitCode = code;
    for (const id of [...pending.keys()]) settle(id, null);
  });
  child.stdin.on("error", () => {});
  child.stderr.on("data", (chunk) => { session.stderr = bounded(session.stderr + chunk, 4000); });
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    let newline;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (!line) continue;
      let message;
      try { message = JSON.parse(line); } catch { continue; }
      if (message?.type === "control_response") settle(message.response?.request_id, message.response);
    }
  });
  session.request = (request) => new Promise((done) => {
    if (session.exited) return done(null);
    const id = `smoke-${next++}`;
    const timer = setTimeout(() => settle(id, null), REQUEST_TIMEOUT_MS);
    pending.set(id, { done, timer });
    child.stdin.write(`${JSON.stringify({ type: "control_request", request_id: id, request })}\n`);
  });
  session.stop = () => {
    child.stdin.end();
    if (!session.exited) child.kill("SIGTERM");
  };
  return session;
}

function serverStatuses(servers, expected) {
  const byName = new Map((Array.isArray(servers) ? servers : []).map((server) => [server?.name, server]));
  return Object.fromEntries(expected.map((name) => {
    const server = byName.get(`plugin:${PLUGIN}:${name}`);
    return [name, server?.source === "plugin" ? String(server.status ?? "unknown") : "missing"];
  }));
}

async function smoke(request) {
  const { projectRoot, config, identity, signal } = request;
  const expected = Array.isArray(config?.expectConnected) ? config.expectConnected : [];
  const evidence = [];
  const finish = (status, summary) => ({ schemaVersion: 1, status, summary, identity, evidence });
  if (!expected.length) return finish("incomplete", "config.expectConnected names no MCP servers");

  const project = realpathSync(mkdtempSync(join(tmpdir(), `${PLUGIN}-smoke-`)));
  const args = [
    "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
    // --plugin-dir already wins over a same-named installed copy; the session-only setting also
    // turns off the nmg-plugins install so the result never depends on what is installed.
    "--plugin-dir", projectRoot, "--settings", JSON.stringify({ enabledPlugins: { [`${PLUGIN}@nmg-plugins`]: false } }),
  ];
  let session = null;
  const cancel = () => session?.stop();
  signal?.addEventListener("abort", cancel, { once: true });
  try {
    evidence.push(commandEvidence(`git init (ephemeral test project ${project})`, await run("git", ["init", "-q"], { cwd: project, signal })));
    if (signal?.aborted) return finish("incomplete", "plugin session smoke cancelled");
    session = startSession(args, { cwd: project });

    const deadline = Date.now() + STATUS_TIMEOUT_MS;
    let servers = [];
    let statuses = serverStatuses(servers, expected);
    let answered = false;
    while (Date.now() < deadline) {
      if (signal?.aborted) return finish("incomplete", "plugin session smoke cancelled");
      const response = await session.request({ subtype: "mcp_status" });
      if (response?.subtype === "success") {
        answered = true;
        servers = response.response?.mcpServers ?? [];
        statuses = serverStatuses(servers, expected);
        if (Object.values(statuses).every((status) => TERMINAL.has(status))) break;
      }
      if (session.exited) break;
      await sleep(POLL_MS);
    }
    evidence.push({
      kind: "command",
      summary: `claude ${args.slice(0, 6).join(" ")} --plugin-dir ${projectRoot} (mcp_status control requests)`,
      artifact: null,
      stdout: bounded(JSON.stringify(servers.filter((server) => String(server?.name).startsWith(`plugin:${PLUGIN}:`))
        .map(({ name, status, error, source }) => ({ name, status, error, source })), null, 1)),
      stderr: bounded(session.spawnError ?? session.stderr, 4000),
    });
    if (session.spawnError) return finish("incomplete", `claude CLI could not be started: ${session.spawnError}`);
    if (!answered) {
      return finish("failed", session.exited
        ? `Claude Code session with --plugin-dir exited (code ${session.exitCode}) before reporting MCP status`
        : "Claude Code session with --plugin-dir did not report MCP status");
    }
    const summary = expected.map((server) => `${PLUGIN}:${server} ${statuses[server]}`).join(", ");
    return Object.values(statuses).every((status) => status === "connected")
      ? finish("passed", `plugin loaded via --plugin-dir; ${summary}`)
      : finish("failed", `plugin MCP servers not all connected: ${summary}`);
  } finally {
    signal?.removeEventListener("abort", cancel);
    session?.stop();
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
