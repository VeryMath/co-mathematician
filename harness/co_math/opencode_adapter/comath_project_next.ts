import { tool } from "@opencode-ai/plugin"
import { runCore } from "../co-math/runner"

export default tool({
  description: "Explain the current Co-Math project state and one useful next action.",
  args: {
    project: tool.schema.string().optional().describe("Project path; defaults to the current OpenCode directory"),
  },
  async execute(args, context) {
    const project = args.project ?? context.directory
    return runCore(["next", "--project", project, "--json"], context.directory)
  },
})
