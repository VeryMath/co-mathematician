# Reusing Workstream Inputs

English | [中文说明](artifact-reuse.zh-CN.md)

Keep an upstream result at its existing workspace path and read it from there.
New workstreams can record those paths without copying the files:

```bash
co-math new-workstream \
  --workspace workspace \
  --goal-id G1 \
  --title "Analyze existing results" \
  --kind computation \
  --input workstreams/WS-G1-001-search/artifacts/results.csv \
  --input workstreams/WS-G1-001-search/report.md
```

The goal must already be approved and each input must be an existing file
inside the workspace. Paths are relative to `workspace/`, regardless of the
shell's current directory. Forward slashes and Windows path separators are
accepted. Invalid input paths are rejected before creating the workstream.
Repeating the same path records it once.

## Storage Layout

```text
workspace/workstreams/
  WS-G1-001-search/
    artifacts/results.csv
    report.md
  WS-G1-002-analyze-existing-results/
    inputs.md
    artifacts/
```

`inputs.md` contains relative Markdown links to the selected files. The upstream
file stays in one place, even when many workstreams reference it. New outputs
belong in the consuming workstream's own `artifacts/` directory. This also works
for large binary files; creating the reference does not read the file contents.

Relative links survive moving the whole workspace with its directory structure
intact. They need neither hard links nor symbolic links, so the same layout can
be used on Windows, macOS, and Linux.

## Reading And Editing

Treat shared inputs as read-only. This is a working convention, not a filesystem
permission change: editing the source changes what every reference reads.
Renaming or removing the source breaks the references. Keep upstream paths
stable and record the input paths in reports when explaining a computation.

When an experiment needs to modify its input independently, make an explicit
copy into that workstream and explain the reason in its notes. Sharing a path
does not provide an independent input snapshot.

## Existing Projects

Existing input directories and research evidence stay as they are. The new
option only affects workstreams that use `--input`; old CLI calls still work.

For future work, point at an existing upstream file instead of making another
`artifacts/input/` copy. There is no automatic scan, deduplication, deletion, or
migration of existing copies. Any later cleanup needs a separate decision about
which files and historical references must be retained.

This addresses new path-based reuse discussed in
[issue #7](https://github.com/VeryMath/co-mathematician/issues/7). The issue's
reported storage measurements came from the reporter's workspace and have not
been reproduced in this repository.
