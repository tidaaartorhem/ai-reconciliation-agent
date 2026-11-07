/**
 * prepare-public.cjs — runs as part of `npm run build` (before `vite build`).
 *
 * 1. Runs the Python pipeline: ../scripts/build_web.py (preferring the
 *    repo venv at ../.venv/bin/python, falling back to python3).
 *    Rebuilds web/public/data/*.json from the real Olist Q4 2017 break
 *    queue, proving the shipped payloads are pipeline-generated.
 * 2. Writes web/public/data/stamp.json with repo, git sha, UTC build time.
 * 3. Exits non-zero if the pipeline produced no orders.
 */
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const WEB_DIR = path.resolve(__dirname, "..");
const ROOT_DIR = path.resolve(WEB_DIR, "..");
const PUBLIC_DATA = path.join(WEB_DIR, "public", "data");

function fail(msg) {
  console.error(`prepare-public: ${msg}`);
  process.exit(1);
}

function gitSha() {
  try {
    return execFileSync("git", ["-C", ROOT_DIR, "rev-parse", "--short", "HEAD"], {
      encoding: "utf8",
    }).trim();
  } catch {
    return "unknown";
  }
}

const venvPython = path.join(ROOT_DIR, ".venv", "bin", "python");
const python = fs.existsSync(venvPython) ? venvPython : "python3";

console.log(`prepare-public: running ${python} ../scripts/build_web.py ...`);
try {
  execFileSync(python, ["../scripts/build_web.py"], {
    cwd: WEB_DIR,
    stdio: "inherit",
  });
} catch (e) {
  fail(`pipeline script failed (${e && e.message ? e.message : e})`);
}

const orders = path.join(PUBLIC_DATA, "orders.json");
if (!fs.existsSync(orders)) {
  fail("orders.json missing after pipeline run");
}
const rows = JSON.parse(fs.readFileSync(orders, "utf8"));
if (!Array.isArray(rows) || rows.length === 0) {
  fail("orders.json is empty");
}
console.log(`prepare-public: ${rows.length} orders shipped`);

const stamp = {
  repo: "tidaaartorhem/ai-reconciliation-agent",
  git_sha: gitSha(),
  built_utc: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
  pipeline: "recondesk LangGraph intake->reconcile->score->route->draft->gate (zero LLM calls)",
};
fs.writeFileSync(path.join(PUBLIC_DATA, "stamp.json"), JSON.stringify(stamp, null, 1));
console.log(`prepare-public: stamp ${stamp.git_sha}`);
