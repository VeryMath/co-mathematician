import { tool } from "@opencode-ai/plugin"
import { requireAllowedTarget, runCore } from "../co-math/runner"

export default tool({
  description: "Archive or reopen a Co-Math project without deleting research files.",
  args: {
    action: tool.schema.enum(["archive", "reopen"]),
    project: tool.schema.string().optional().describe("Project path; defaults to the current OpenCode directory"),
  },
  async execute(args, context) {
    const project = await requireAllowedTarget(args.project ?? context.directory)
    return runCore([args.action, "--project", project, "--json"], context.directory)
  },
})
