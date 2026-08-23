import { tool } from "@opencode-ai/plugin"
import { requireAllowedTarget, runCore } from "../co-math/runner"

export default tool({
  description: "Create a new independent Co-Math research project.",
  args: {
    name: tool.schema.string().min(1).describe("Project display name"),
    language: tool.schema.enum(["en", "user-notes", "user-readable", "match"]),
    path: tool.schema.string().optional().describe("Optional absolute project directory"),
    initializeGit: tool.schema.boolean().optional().describe("Initialize an independent Git repository"),
  },
  async execute(args) {
    const command = ["new", args.name, "--language", args.language, "--json"]
    if (args.path) command.push("--path", await requireAllowedTarget(args.path))
    if (args.initializeGit === false) command.push("--no-git")
    return runCore(command)
  },
})
