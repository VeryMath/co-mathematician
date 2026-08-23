import { tool } from "@opencode-ai/plugin"
import { runCore } from "../co-math/runner"

export default tool({
  description: "List registered Co-Math projects and their projected status.",
  args: {},
  async execute() {
    return runCore(["list", "--json"])
  },
})
