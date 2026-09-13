# Dashboard instructions

Read [../AGENTS.md](../AGENTS.md) first. Its scope, secret-handling, and backend
invariants also apply here. Before UI changes read
[the design baseline](../_docs/design-system.md); before tests read
[the testing guide](../_docs/testing-guidelines.md).

Use `npm ci`, `npm run typecheck`, `npm run build`, and `npm test` in this directory.
Browser tests use temporary synthetic records and a scripted fake; never point
them at the live model-enabled API. Keep the provider key server-side in Python.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
