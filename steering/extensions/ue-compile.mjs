// UE compile gate for nmg-game-dev. Builds the DogfoodEditor target of fixtures/dogfood.uproject
// with the engine's Build.sh, which compiles the nmg-game-dev UE plugin (its runtime, editor and
// automation-spec sources) against UE 5.8 without starting the editor. Build output lands in the
// ignored Binaries/ and Intermediate/ folders, so the tree stays clean. Build.sh changes its own
// working directory, so the project path is made absolute from the request's projectRoot. Only
// Node built-ins are imported, so the steering writer can load this module from its staged copy.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";

const DEFAULT_UE_ROOT = "/Users/Shared/Epic Games/UE_5.8";
const ERROR_LINE = /\berror\b|\bfatal\b/i;

function tail(value, size = 8000) {
  const text = String(value ?? "");
  return text.length <= size ? text : `[truncated]\n${text.slice(-size)}`;
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

async function compile(request) {
  const { projectRoot, config, identity, signal } = request;
  const evidence = [];
  const finish = (status, summary) => ({ schemaVersion: 1, status, summary, identity, evidence });
  if (process.platform !== "darwin") return finish("incomplete", "gate-ue-compile runs on macOS hosts only");

  const ueRoot = process.env.UE_ROOT || DEFAULT_UE_ROOT;
  const buildSh = join(ueRoot, "Engine", "Build", "BatchFiles", "Mac", "Build.sh");
  if (!existsSync(buildSh)) return finish("incomplete", `Build.sh not found at ${buildSh}; install UE 5.8 or set UE_ROOT`);
  const project = resolve(projectRoot, typeof config?.project === "string" ? config.project : "fixtures/dogfood.uproject");
  if (!existsSync(project)) return finish("incomplete", `project not found: ${project}`);
  const target = typeof config?.target === "string" ? config.target : "DogfoodEditor";

  const args = [target, "Mac", "Development", `-Project=${project}`, "-WaitMutex"];
  const output = await run(buildSh, args, { cwd: projectRoot, signal });
  const errors = `${output.stdout}\n${output.stderr}`.split("\n").filter((line) => ERROR_LINE.test(line)).slice(0, 60).join("\n");
  evidence.push({
    kind: "command",
    summary: `${buildSh} ${args.join(" ")}`,
    artifact: null,
    stdout: tail(output.stdout),
    stderr: tail(errors || output.stderr, 4000),
  });
  if (signal?.aborted) return finish("incomplete", "gate-ue-compile cancelled");
  if (output.status === 0) return finish("passed", `${target} compiled against ${ueRoot}`);
  if (output.status === null) return finish("incomplete", `Build.sh did not run: ${tail(output.stderr, 500)}`);
  const first = errors.split("\n").find(Boolean) ?? "no error line found";
  return finish("failed", `${target} failed to compile (exit ${output.status}): ${first}`);
}

export const extension = Object.freeze({
  schemaVersion: 1,
  id: "project.ue-compile",
  providers: Object.freeze({
    "project.ue-compile": compile,
  }),
});
