# How to use this book

This book is for external developers who already use Git, a terminal, and at least one agent development
tool. You do not need to read the LoopX Kernel source or learn every CLI subcommand first.

## What you will accomplish

The first six chapters establish one control-plane model. The book then branches into two independent
practice paths:

```text
Control-plane foundations
├── Connect an existing Git project
└── Make a developer contribution
    ├── Control Plane, Capabilities, and Domain State
    ├── Providers, Hosts/Runners, projections, docs, and fixtures
    └── Extensions and independent package lifecycle
```

The foundation sequence covers:

1. why one session is insufficient for long-running work;
2. which state belongs to an agent session, a Host Goal, and LoopX;
3. canonical state, workbenches, events, and read-only projections;
4. Todo graphs, Gates, claims, leases, authority, and peer collaboration;
5. how one governed Turn is decided, executed, validated, and written back;
6. retry, replan, self-repair, terminal closure, and runtime boundaries.

After those chapters:

- to manage your own repository, start with
  [Connect an existing Git project](./05-connect-existing-project.md);
- to make any public LoopX contribution, start with the
  [Developer contribution map](./source-protocol-map.md);
- once you know the contribution needs independent installation, activation, and upgrades, continue to
  [Choose the right extension point](./08-extension-placement.md).

The paths share the same foundations but do not depend on each other. Extension lifecycle is one
developer-contribution path, not the default destination for every contribution.

## How chapters are organized

Each chapter prioritizes four questions:

1. What job does the reader need to complete now?
2. What observable result proves success?
3. Which concepts are necessary to predict the behavior?
4. Where should the reader recover when the normal path fails?

Command snippets fall into three categories:

- **Runnable:** checked against the stated LoopX baseline.
- **Based on the official scaffold:** the example focuses on the domain changes, protocol, and validation
  needed for the task without a separate exercise repository.
- **Simplified for explanation:** illustrates a state relationship and must not be pasted into production
  configuration.

## Sources of authority

The English and Chinese editions share the same product facts. The Chinese root edition is the editorial
source of truth; the English edition is organized for English-speaking external developers rather than
maintained as a separate product specification.

| Subject | Authority |
| --- | --- |
| CLI arguments, protocols, and runtime behavior | LoopX releases, current `--help`, and the official repository |
| Learning path, scaffold guidance, explanations, and trade-off guidance | This book |
| Facts about your project | Git, CI, external services, and project-owned sources |

When the book and a current release disagree, follow the release first and report the documentation drift.
Do not bypass a newer permission or lifecycle check just to make an older example pass.

## Version baseline

The current release anchor is LoopX GitHub release `v0.4.1`. Local command examples were checked against
the installed `loopx 0.4.0` CLI surface. A release tag, installed CLI, and source checkout can be on
different revisions, so verify these surfaces against your actual environment:

- install and update;
- Host activation;
- the `start-goal` guided packet;
- Codex App heartbeat and visible Codex CLI Goal behavior;
- Extension manifest and lifecycle commands.

Before running commands from the book:

```bash
loopx --version
loopx doctor
```

If your version differs, inspect current command help and release notes before deciding whether you found
documentation drift, a release difference, or a product behavior change. This book does not guess what
different version identifiers imply.

## Deliberate scope

The developer-contribution path covers placement, protocol maps, rule changes, Capabilities and Providers,
Hosts and Runners, projections, documentation and fixtures, Extension lifecycle, validation, and PR
delivery. It does not duplicate the complete nine-lesson maintainer course or a full CLI reference.
Production effectful Providers, private organizational cases, and live benchmark operation remain outside
the main path. Use official source, protocol documentation, and the target project's own facts for those
workflows.
