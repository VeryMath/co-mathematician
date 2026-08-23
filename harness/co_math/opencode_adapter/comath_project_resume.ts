import { tool } from "@opencode-ai/plugin"
import { runCore } from "../co-math/runner"

export default tool({
  description: "Reconstruct durable Co-Math project context and the next valid gate.",
  args: {
    project: tool.schema.string().optional().describe("Project path; defaults to the current OpenCode directory"),
  },
  async execute(args, context) {
    const project = args.project ?? context.directory
    return runCore(["resume", "--project", project, "--json"], context.directory)
  },
})
