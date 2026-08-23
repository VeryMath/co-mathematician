import { tool } from "@opencode-ai/plugin"
import { requireAllowedTarget, runCore } from "../co-math/runner"

export default tool({
  description: "Adopt an existing legacy Co-Math workspace without moving or rewriting its research files.",
  args: {
    path: tool.schema.string().min(1).describe("Existing project directory"),
  },
  async execute(args) {
    const target = await requireAllowedTarget(args.path)
    return runCore(["adopt", target, "--json"])
  },
})
