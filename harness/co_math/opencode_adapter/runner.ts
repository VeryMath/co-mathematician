import path from "node:path"
import os from "node:os"
import { readFile } from "node:fs/promises"

type CoMathConfig = {
  cli_path: string
  projects_home: string
  allowed_project_roots: string[]
}

const configUrl = new URL("./config.json", import.meta.url)

async function loadConfig(): Promise<CoMathConfig> {
  const config = JSON.parse(await readFile(configUrl, "utf8")) as CoMathConfig
  if (!path.isAbsolute(config.cli_path) || !path.isAbsolute(config.projects_home)) {
    throw new Error("Invalid Co-Math OpenCode adapter configuration")
  }
  if (
    !Array.isArray(config.allowed_project_roots) ||
    config.allowed_project_roots.length === 0 ||
    !config.allowed_project_roots.every((root) => typeof root === "string" && path.isAbsolute(root))
  ) {
    throw new Error("Co-Math allowed project roots must be absolute paths")
  }
  return config
}

function expandHome(value: string): string {
  if (value === "~") return os.homedir()
  if (value.startsWith(`~${path.sep}`)) return path.join(os.homedir(), value.slice(2))
  return value
}

function comparable(value: string): string {
  const resolved = path.resolve(value)
  return process.platform === "win32" ? resolved.toLowerCase() : resolved
}

function isWithin(candidate: string, root: string): boolean {
  const relative = path.relative(comparable(root), comparable(candidate))
  return relative === "" || (
    relative !== ".." &&
    !relative.startsWith(`..${path.sep}`) &&
    !path.isAbsolute(relative)
  )
}

export async function requireAllowedTarget(value: string): Promise<string> {
  const config = await loadConfig()
  const candidate = path.resolve(expandHome(value))
  if (!config.allowed_project_roots.some((root) => isWithin(candidate, root))) {
    throw new Error(`Target is outside Co-Math allowed project roots: ${candidate}`)
  }
  return candidate
}

export async function runCore(args: string[], cwd?: string): Promise<string> {
  const config = await loadConfig()
  const child = Bun.spawn([config.cli_path, ...args], {
    cwd,
    stdout: "pipe",
    stderr: "pipe",
  })
  const [stdout, stderr, exitCode] = await Promise.all([
    new Response(child.stdout).text(),
    new Response(child.stderr).text(),
    child.exited,
  ])
  if (exitCode !== 0) {
    const detail = stderr.trim() || stdout.trim() || "no diagnostic output"
    throw new Error(`co-math failed with exit code ${exitCode}: ${detail}`)
  }
  return stdout.trim()
}
