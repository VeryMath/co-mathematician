import { tool } from "@opencode-ai/plugin"
import { requireAllowedTarget, runCore } from "../co-math/runner"

export default tool({
  description: "Inspect a Co-Math project without modifying its files.",
  args: {
    project: tool.schema.string().optional().describe("Project path; defaults to the current OpenCode directory"),
  },
  async execute(args, context) {
    const project = await requireAllowedTarget(args.project ?? context.directory)
    return runCore(["status", "--project", project, "--json"], context.directory)
  },
})
