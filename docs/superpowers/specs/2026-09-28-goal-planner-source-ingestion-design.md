# Goal Planner source ingestion design

## Purpose

Let an operator paste notes or drag source documents into Goal Planner. On
Plan, Hermes extracts the source text, asks the Goal Planner model configured
in Settings to derive an implementation plan, and immediately creates ordered
Work Hub items. The default boilerplate planning template is replaced by
task-specific items such as Frontend, Backend, Data, QA, and Docs.

## Scope

- Accept typed or pasted notes and temporary PDF, DOCX, TXT, and Markdown
  uploads in Goal Planner.
- Use the Goal Planner Settings model, rather than the active chat model.
- Create items immediately after one successful planning response.
- Delete uploads after extraction on every exit path.
- Preserve existing manual Work Hub item creation and existing workflow runs.

## UI

The planner input becomes a dashed drop zone. Its empty state is centered in
both axes and reads: `Create, Paste, or Attach notes to be turned into a
structured item`.

Dragging compatible files over the zone animates its border and glow with
reduced-motion support. Uploaded files appear as removable chips. Planning
shows progress and then opens the generated Work Hub items.

## Data flow

1. Browser creates a one-time planner upload for each dropped file.
2. Server validates ownership, type, file size, and text-extraction limits.
3. Server extracts text into an in-memory, request-scoped source bundle.
4. Planner notes and extracted text are sent to the configured Goal Planner
   model with a structured-output schema.
5. Server validates returned items, rejects malformed or duplicate content,
   sorts dependency-safe work, and atomically creates Work Hub items.
6. Server deletes temporary uploads in `finally`, whether planning succeeds,
   fails, or is cancelled.

Files and extracted source text do not enter chat history, the project
workspace, or durable Work Hub item metadata. Generated items keep only a
short, model-produced source summary when useful for execution context.

## Model output and ordering

Each model item must contain a concise title, category, description,
priority, dependencies, and acceptance criteria. Categories are guidance, not
fixed templates. The planner may emit Frontend, Backend, Data, QA, Docs, or
domain-specific categories.

The server performs a topological dependency sort. Items at the same dependency
level are ordered by category and priority. A cycle, unknown dependency,
invalid schema, empty item list, or duplicate normalized title fails the whole
request; no partial items are created.

Created items inherit the Goal Planner Settings agent profile so later Work
Hub workflows use the intended configured model/profile.

## Error handling and lifecycle

- Unsupported, encrypted, unreadable, or oversized files show an actionable
  error and create no work items.
- Missing planner model configuration fails before invoking the model.
- Model/network errors create no work items and remove all uploads.
- Browser cancellation deletes unconsumed uploads through an explicit cleanup
  endpoint; expiry cleanup covers abandoned uploads.
- Upload tokens are bound to the authenticated browser session and expire
  quickly. Paths are never accepted from the browser.

## Verification

Automated coverage will include upload ownership/expiry, TXT/PDF/DOCX
extraction, structured-output validation, dependency ordering, atomic failure,
cleanup on all exits, settings-model selection, and UI drag/drop states.
Manual checks will cover desktop, narrow, and mobile layouts plus reduced
motion.
