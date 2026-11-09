# Objective

Build a complete modern **Notes module** inside the existing Hermes WebUI using **BlockNote** as the core editor.

I have attached/downloaded the BlockNote project into this workspace so you can inspect its source code, examples, components, editor configuration, styling patterns, extensions, and implementation details.

The goal is **NOT** to merge or copy the entire BlockNote application/repository into Hermes WebUI.

Instead:

- Use BlockNote as the rich-text/block editor engine.
- Study the attached BlockNote repository for correct implementation patterns.
- Integrate BlockNote cleanly into the architecture and design system already used by Hermes WebUI.
- Build the surrounding Notes experience ourselves.
- Keep the feature modular so it can later integrate deeply with Hermes agents, projects, tasks, files, and orchestration.

Before modifying anything, inspect the existing Hermes WebUI architecture and the attached BlockNote repository.

---

# Phase 1 — Inspect the Existing Project

Before writing code, inspect:

1. The existing frontend architecture.
2. Routing structure.
3. Current page/layout components.
4. Existing sidebar/navigation system.
5. State-management solution.
6. Backend/API architecture.
7. Database/storage implementation.
8. Authentication/user architecture if present.
9. Existing theme variables and design tokens.
10. Existing reusable UI components.
11. Existing animation libraries.
12. Existing icons.
13. Existing project/task/agent models.
14. Current Notes or Sticky Notes implementation, if one already exists.

Do not introduce unnecessary frameworks if equivalent functionality already exists.

Prefer existing dependencies and patterns.

Also inspect the attached BlockNote repository and determine:

- Required BlockNote packages.
- Recommended React implementation.
- BlockNote editor initialization.
- Theme customization options.
- Slash menu implementation.
- Formatting toolbar implementation.
- File/image handling.
- Custom blocks.
- Block serialization.
- Markdown/HTML conversion capabilities.
- Persistence patterns.
- Extension APIs.
- Relevant examples.
- Any licensing-sensitive packages.

Use the normal/open-source BlockNote packages unless there is a clear reason otherwise.

Do not introduce BlockNote XL/GPL components without explicitly identifying them first.

---

# Phase 2 — Architecture

The Notes module should be a native part of Hermes WebUI.

Conceptually:

```text
Hermes WebUI
│
├── Chat
├── Office
├── Projects
├── Agents
├── Tasks
├── Notes
│   │
│   ├── Notes Navigation
│   │
│   ├── Search
│   ├── Folders / Projects
│   ├── Tags
│   ├── Favorites
│   ├── Recent Notes
│   └── BlockNote Editor
│
└── Backend / Storage
```

Do not iframe an external application.

Do not run BlockNote as a second standalone frontend.

BlockNote should function as an internal editor component within Hermes WebUI.

---

# Phase 3 — Notes Page Layout

Create a dedicated Notes page.

Use the existing Hermes WebUI visual language.

The Notes interface should feel modern, minimal, technical, and consistent with the rest of the application.

Use a three-section layout where appropriate:

```text
┌──────────────────────────────────────────────────────────────┐
│ Notes                                      Search   + New    │
├───────────────┬──────────────────┬───────────────────────────┤
│ Navigation    │ Notes List       │ Editor                    │
│               │                  │                           │
│ All Notes     │ Project Ideas    │ Project Architecture      │
│ Favorites     │ API Design       │                           │
│ Recent        │ Office Fixes     │ [BlockNote Editor]        │
│               │ Database Notes   │                           │
│ Projects      │                  │                           │
│ Tags          │                  │                           │
│ Archive       │                  │                           │
└───────────────┴──────────────────┴───────────────────────────┘
```

The exact layout can adapt to the existing Hermes design.

Do not force this layout if the application's current component structure suggests a cleaner solution.

---

# Phase 4 — Notes Navigation

Create a Notes navigation section containing:

- All Notes
- Recent
- Favorites
- Pinned
- Archive
- Trash

Also support:

## Project-based notes

Notes should optionally belong to a Hermes project.

Example:

```text
Projects

Hermes WebUI
JobOS
Temani
Personal
Unassigned
```

Selecting a project filters notes belonging to that project.

Reuse existing project entities rather than creating duplicate project records.

---

# Phase 5 — Notes List

The Notes list should display useful metadata without looking cluttered.

Each note item can display:

- Note title
- Short preview
- Last updated
- Project
- Tags
- Favorite indicator
- Pinned indicator

Example:

```text
Project Architecture

Design for the new orchestration...
Hermes WebUI • 3m ago

#architecture #backend
```

The currently selected note should have a subtle active state.

Avoid excessive gradients, glowing borders, or unnecessary effects.

Keep it aligned with the clean technical style of Hermes WebUI.

---

# Phase 6 — BlockNote Editor

Use BlockNote for the actual content editor.

The editor should support at minimum:

- Paragraphs
- Headings
- Bullet lists
- Numbered lists
- Checklists
- Quotes
- Code blocks
- Inline code
- Bold
- Italic
- Underline where supported
- Links
- Images
- Files/attachments if practical
- Tables if supported by the selected BlockNote packages
- Block drag-and-drop
- Slash commands
- Block manipulation
- Undo/redo

Use BlockNote's intended architecture rather than recreating these features manually.

The editor must blend visually into Hermes WebUI.

Remove unnecessary BlockNote demo styling.

Customize:

- Background
- Typography
- Borders
- Menus
- Slash menu
- Formatting toolbar
- Hover states
- Selected blocks
- Drag handles
- Popovers
- Placeholder text

Use Hermes design tokens wherever possible.

---

# Phase 7 — Note Title

The note title should exist separately from the main BlockNote body.

Example:

```text
Project Architecture
────────────────────────────────────

Start writing...
```

Title behavior:

- Editable inline.
- Autosaves.
- Empty notes can display "Untitled".
- The title should appear in the Notes list.
- Do not store the title as a normal BlockNote paragraph unless there is a strong architectural reason.

---

# Phase 8 — Autosave

Notes should autosave.

Avoid requiring the user to manually click Save.

Recommended behavior:

```text
Editing
   ↓
debounce
   ↓
Save
   ↓
Saved
```

Show a small status indicator such as:

```text
Saving...
Saved
```

Do not save on every keystroke without debouncing.

Use an appropriate debounce period, approximately 500–1500 ms depending on the existing application architecture.

Prevent race conditions where an older request overwrites a newer note state.

---

# Phase 9 — Data Model

Design a proper Notes model.

Adapt this to the application's existing backend/database structure.

Conceptually:

```typescript
Note {
  id
  title
  content
  createdAt
  updatedAt

  projectId?
  createdBy?

  isFavorite
  isPinned
  isArchived
  isDeleted

  tags[]

  metadata?
}
```

Store BlockNote's native document structure rather than flattening everything into plain text.

For example, content may contain BlockNote's block JSON.

Also consider storing generated plain-text content separately if needed for search or AI indexing.

Do not duplicate unnecessary content.

---

# Phase 10 — CRUD

Implement full note management.

Required actions:

- Create note
- Edit note
- Rename note
- Delete note
- Restore deleted note
- Permanently delete note
- Duplicate note
- Pin/unpin
- Favorite/unfavorite
- Archive/unarchive

Use contextual menus rather than filling the interface with buttons.

Example:

```text
⋯
Rename
Duplicate
Move to project
Favorite
Archive
Delete
```

---

# Phase 11 — Search

Create fast note search.

Search should cover:

- Titles
- Note contents
- Tags
- Projects

Search should update dynamically as the user types.

Highlighting matched results is optional.

Design the implementation so semantic/AI search can be added later.

---

# Phase 12 — Tags

Allow notes to have multiple tags.

Example:

```text
#frontend
#bug
#architecture
#idea
```

Users should be able to:

- Add tags
- Remove tags
- Filter by tag
- Search by tag

Avoid building an overly complicated tagging system.

---

# Phase 13 — Keyboard Shortcuts

Add sensible keyboard shortcuts where appropriate.

At minimum consider:

```text
Ctrl/Cmd + N      New note
Ctrl/Cmd + S      Manual save fallback
Ctrl/Cmd + K      Notes search
Ctrl/Cmd + Shift + F   Global note search
```

Do not override existing Hermes shortcuts.

Inspect the application first.

---

# Phase 14 — Slash Commands

Use BlockNote's slash menu.

Retain standard commands such as:

```text
/text
/heading
/bullet
/numbered
/checklist
/code
/quote
/image
/table
```

Then create an architecture that allows Hermes-specific commands later.

Do NOT implement fake agent actions that do nothing.

However, prepare the extension structure for future commands such as:

```text
/ask-agent
/summarize
/send-to-agent
/create-task
/implement
/explain
/fix-code
```

If there is already a clean agent API available in the project, implementing a small first integration is acceptable.

Otherwise keep these as future extension points.

---

# Phase 15 — Hermes Agent Integration Architecture

Notes will eventually become part of Hermes' agent workflow.

Design the module with this in mind.

A note should eventually be able to become agent context.

Example workflow:

```text
User writes note

        ↓

"Fix white artifacts around platforms."

        ↓

Send to Agent

        ↓

Select:
Codex
Claude
Hermes
Other Agent

        ↓

Agent receives:
- Note title
- Note content
- Project context
- Attached files
- Relevant metadata
```

Do not tightly couple the editor directly to one AI provider.

Use Hermes' existing orchestration layer.

Create clean abstractions such as:

```text
Notes
   ↓
Context / Action Layer
   ↓
Hermes Orchestrator
   ↓
Agent
```

This will allow multiple agents later.

---

# Phase 16 — Note Action Bar

Add a subtle action area around the note.

Potential actions:

```text
Favorite
Pin
Share
Export
More
AI
```

AI should not dominate the Notes experience.

Notes should still work perfectly without invoking an agent.

---

# Phase 17 — Selection AI Actions

Prepare BlockNote so selected text can eventually be sent to Hermes.

For example, when text is highlighted, a contextual action could eventually offer:

```text
Ask Hermes
Explain
Improve Writing
Summarize
Turn Into Tasks
Send to Agent
```

If agent APIs are already available and straightforward to reuse, implement this cleanly.

Otherwise create only the UI architecture/hooks required for future integration.

Avoid placeholder controls that appear functional but do nothing.

---

# Phase 18 — Convert Note Into Task

Because Hermes already deals with projects/tasks, design notes so they can eventually generate tasks.

Example:

```text
[x] Create database schema
[ ] Build API endpoint
[ ] Add editor
```

Potential future action:

```text
Create Tasks
```

which could turn selected checklist blocks into actual Hermes tasks.

For the current implementation, prioritize architecture compatibility.

Do not build a second task-management system inside Notes.

Reuse existing Hermes task entities.

---

# Phase 19 — Project Context

If the user opens Notes from inside a particular project, support automatically associating the new note with that project.

Example:

```text
Projects
  └── Hermes WebUI
       └── Notes
```

New note:

```text
Project: Hermes WebUI
```

If Notes is opened globally:

```text
Project: Unassigned
```

Users should be able to change the project later.

---

# Phase 20 — Responsive Behavior

The Notes page must remain usable on smaller screens.

Desktop:

```text
Navigation | Notes List | Editor
```

Medium width:

```text
Notes List | Editor
```

with navigation collapsible.

Mobile:

```text
Notes
 ↓
Note List
 ↓
Editor
```

Use drawers/sliding panels where appropriate.

Do not cram three panels onto a narrow viewport.

---

# Phase 21 — Empty States

Create polished empty states.

Examples:

No notes:

```text
No notes yet.

Create your first note to get started.

[ New Note ]
```

No search results:

```text
No notes found for "orchestration".
```

No project notes:

```text
No notes in this project.
```

Avoid unnecessary illustrations unless the existing UI uses them.

---

# Phase 22 — Loading States

Implement proper loading states.

Avoid content flashing.

Use existing Hermes loading/skeleton components where possible.

Handle:

- Initial Notes page loading
- Note list loading
- Note loading
- Saving
- Search
- Deleting
- Restoring

---

# Phase 23 — Error Handling

Handle common failures cleanly.

Examples:

- Note failed to load
- Note failed to save
- Backend unavailable
- File upload failed
- Search failed

Do not lose unsaved note content due to a temporary backend error.

Retain the current editor state and allow retry.

---

# Phase 24 — File and Image Support

Inspect BlockNote's recommended file/image implementation.

If Hermes already has file storage, reuse it.

Do not introduce an unrelated storage service unnecessarily.

Images should preferably support:

- Upload
- Paste
- Drag/drop

Store only URLs/IDs in the note document rather than large binary data.

---

# Phase 25 — Note Export

If straightforward using BlockNote's existing APIs, support exporting notes as:

- Markdown
- HTML
- JSON

PDF can be added later unless the project already has an export system.

---

# Phase 26 — Import

If BlockNote provides clean conversions, allow future support for importing:

- Markdown
- HTML

Do not prioritize complex import compatibility over the core Notes experience.

---

# Phase 27 — Persistence

The user should never unexpectedly lose the current note.

Consider:

- Autosave
- Local temporary state
- Server persistence
- Recovery from failed save

If the application's architecture supports local caching, use it appropriately.

Do not create conflicting state sources.

---

# Phase 28 — State Management

Use Hermes WebUI's existing state-management approach.

Do not add Redux/Zustand/etc. unless the project already uses it or there is a clear architectural justification.

Separate:

```text
Editor state
Notes metadata state
UI state
Server state
```

where appropriate.

Avoid giant monolithic components.

---

# Phase 29 — Component Structure

Keep the implementation modular.

A structure similar to this is acceptable:

```text
notes/
├── components/
│   ├── NotesSidebar
│   ├── NotesList
│   ├── NotesListItem
│   ├── NotesEditor
│   ├── NoteHeader
│   ├── NoteActions
│   ├── NoteSearch
│   ├── NoteTags
│   └── NoteStatus
│
├── editor/
│   ├── BlockNoteEditor
│   ├── editorExtensions
│   ├── slashMenu
│   └── serialization
│
├── hooks/
│   ├── useNotes
│   ├── useNote
│   ├── useAutosave
│   └── useNoteSearch
│
├── api/
├── types/
├── utils/
└── index
```

Adapt this to the existing repository conventions.

Do not impose this structure if Hermes already has a better established pattern.

---

# Phase 30 — Performance

BlockNote is a rich editor, so avoid unnecessary rerenders.

Be particularly careful with:

- Editor initialization
- Note switching
- Autosave
- Large notes
- Notes list
- Search
- Project filtering

Do not recreate the editor instance on every render.

Do not constantly deserialize the document unnecessarily.

---

# Phase 31 — Switching Notes

When switching between notes:

1. Make sure pending changes are safely preserved.
2. Load the selected note.
3. Replace editor content correctly.
4. Update metadata.
5. Avoid editor flickering.
6. Avoid creating duplicate editor instances.

Rapidly switching between notes should not cause data loss.

---

# Phase 32 — Theme

BlockNote must match Hermes WebUI.

Inspect existing CSS variables/theme values.

Use them instead of hardcoded styling whenever possible.

Match existing:

- Background colors
- Panel colors
- Borders
- Typography
- Radius
- Shadows
- Spacing
- Hover effects
- Animation timing
- Accent colors

The result should look like BlockNote was built specifically for Hermes.

It should NOT look like an external library embedded inside the application.

---

# Phase 33 — Animations

Use subtle UI animations.

Examples:

- Notes panel opening
- Notes appearing
- Switching notes
- Dropdowns
- Context menus
- Sidebar collapse
- Selected note transition

Do not animate editor text itself unnecessarily.

Reuse the application's existing animation library where available.

---

# Phase 34 — Accessibility

Ensure:

- Keyboard navigation works.
- Tooltips are usable.
- Buttons have accessible labels.
- Focus states remain visible.
- Context menus work with keyboard interaction.
- Contrast remains readable.

Do not break BlockNote's built-in accessibility features while restyling it.

---

# Phase 35 — Existing Sticky Notes

Inspect whether Hermes WebUI currently has a Sticky Notes feature.

If it does, do not immediately delete it.

Determine whether:

A. Sticky Notes should remain a separate quick-note feature.

or

B. It should eventually feed into the main Notes system.

A useful long-term architecture could be:

```text
Sticky Note
     ↓
Convert to Note
     ↓
Full BlockNote document
     ↓
Assign Project
     ↓
Send to Agent
```

Only implement this if it fits the existing architecture cleanly.

---

# Phase 36 — Backend API

If Hermes already has an API structure, create Notes endpoints consistent with it.

Conceptually:

```text
GET    /notes
POST   /notes
GET    /notes/:id
PATCH  /notes/:id
DELETE /notes/:id

POST   /notes/:id/restore

GET    /notes/search
```

The exact endpoints should follow existing backend conventions.

Do not create redundant APIs if equivalent generic resource endpoints already exist.

---

# Phase 37 — Security

Treat note content as user-controlled input.

Ensure:

- HTML output is sanitized where needed.
- Uploaded file types are handled safely.
- File names are not blindly trusted.
- No dangerous HTML/script execution.
- Permissions are respected if multi-user support exists.

Do not weaken existing authentication or authorization.

---

# Phase 38 — Database Migration

If a new database table/collection is required:

Create a proper migration.

Do not manually modify a production database.

Ensure existing data is unaffected.

---

# Phase 39 — Future Search / RAG Compatibility

Design notes so Hermes can later index them for retrieval.

Eventually Hermes should be capable of queries such as:

```text
"What did I write about the office bridge redesign?"

"Find my notes about JobOS."

"Use my Hermes architecture notes as context."
```

You do NOT need to build the entire vector/RAG system now.

However, structure notes so clean text can easily be extracted from the BlockNote JSON later.

Consider utility functions such as:

```typescript
extractPlainText(noteContent)
```

This can later feed:

```text
Embedding
Vector Database
Agent Context
Search
```

---

# Phase 40 — Future Version History

Design persistence in a way that does not prevent future note versioning.

Future capability:

```text
Version History

Today 14:23
Today 13:02
Yesterday 22:18
```

Do not implement full version history unless the current architecture already supports it easily.

---

# Phase 41 — Avoid Overengineering

Do NOT initially implement:

- Google Docs-level collaboration
- CRDT infrastructure
- Massive knowledge graph systems
- Complex backlinks
- Full Obsidian replacement
- Vector databases
- Real-time multiplayer editing
- Advanced publishing systems

unless equivalent infrastructure already exists.

First build an excellent Notes experience.

---

# Phase 42 — MVP Priority

Prioritize implementation in this order:

## Priority 1

Core functionality:

- Notes route/page
- Notes sidebar
- Notes list
- Create note
- Select note
- Delete note
- BlockNote editor
- Note title
- Persistence
- Autosave

## Priority 2

Organization:

- Search
- Project assignment
- Tags
- Favorites
- Pinning
- Archive
- Trash

## Priority 3

Editor polish:

- Theming
- Slash menu customization
- File/image handling
- Tables
- Keyboard shortcuts
- Export

## Priority 4

Hermes integration architecture:

- Send note to agent
- Selection actions
- Create task
- Agent metadata
- Note context APIs

Do not sacrifice core reliability for AI features.

---

# Phase 43 — Testing

Test at minimum:

### Notes

- Create note
- Edit title
- Edit content
- Autosave
- Refresh browser
- Content persists
- Delete
- Restore
- Archive
- Favorite
- Pin

### Editor

- Paragraph
- Headings
- Lists
- Checklist
- Code
- Quote
- Slash menu
- Drag block
- Undo
- Redo

### Switching

- Rapid note switching
- Switching while autosave is pending
- Refresh immediately after editing

### Search

- Search title
- Search content
- Search tags

### Projects

- Assign note
- Change project
- Filter by project
- Delete project behavior

### Responsive

- Large desktop
- Laptop
- Tablet
- Mobile

### Error states

- Failed save
- API unavailable
- Upload failure

---

# Phase 44 — Do Not Break Existing Features

This is extremely important.

Before modifying shared components:

1. Determine where they are used.
2. Preserve backwards compatibility where possible.
3. Avoid large unrelated refactors.
4. Test existing pages after implementation.

The Notes feature should not break:

- Chat
- Office
- Projects
- Agents
- Tasks
- Settings
- Navigation
- Existing APIs

---

# Phase 45 — Docker / Build Environment

Hermes WebUI may be running through Docker.

Inspect the deployment/build setup before modifying dependencies.

After implementation:

- Install required dependencies correctly.
- Update package lock files.
- Rebuild the correct container/image.
- Confirm the running application is using the new build.
- Check browser console.
- Check server logs.
- Check Docker logs if applicable.

Do not assume a source change means the currently running container has rebuilt.

---

# Phase 46 — Code Quality

Requirements:

- TypeScript types should be explicit where practical.
- Avoid `any` unless unavoidable.
- Avoid duplicated logic.
- Avoid giant files.
- Avoid unnecessary abstraction.
- Reuse existing utility functions.
- Remove unused imports.
- Do not leave debugging logs.
- Do not leave dead code.
- Do not leave mock data once real persistence exists.

---

# Phase 47 — Documentation

After completing the implementation, create/update developer documentation covering:

```text
Notes Architecture
BlockNote Integration
Data Model
Autosave
Storage
Search
Project Integration
Agent Integration Extension Points
Files Modified
Dependencies Added
```

Also explain how future developers can add custom BlockNote commands.

---

# Phase 48 — Final Verification

Before considering the work complete:

1. Run the frontend build.
2. Run TypeScript checking.
3. Run linting if configured.
4. Run relevant tests.
5. Inspect console errors.
6. Inspect backend errors.
7. Verify persistence.
8. Verify a fresh browser reload.
9. Verify multiple notes.
10. Verify BlockNote menus.
11. Verify responsive behavior.
12. Verify existing Hermes pages remain functional.

Fix any errors introduced by this implementation.

---

# Desired Final Experience

The final Notes page should feel like a native productivity module inside Hermes rather than a third-party editor.

The user should be able to:

```text
Open Notes
    ↓
Create Note
    ↓
Write using a Notion-style BlockNote editor
    ↓
Assign it to a Hermes project
    ↓
Add tags
    ↓
Search it later
    ↓
Eventually send it directly to an AI agent
```

The architecture should ultimately support:

```text
NOTES
  │
  ├── Human Knowledge
  │
  ├── Project Context
  │
  ├── Ideas
  │
  ├── Instructions
  │
  └── Research
  │
  ▼
HERMES ORCHESTRATION
  │
  ├── Codex
  ├── Claude
  ├── Hermes
  └── Future Agents
```

This means Notes should eventually function as both:

1. A high-quality human note-taking system.
2. A structured knowledge/context source for Hermes agents.

Build the first version with that future direction in mind, but keep the current implementation clean, stable, and reasonably scoped.

---

# Execution Instructions

Start by inspecting the repository.

Do not immediately code.

First identify:

- Existing architecture
- Relevant files
- Existing Notes/Sticky Notes functionality
- Routing
- Database
- Backend APIs
- Project models
- Task models
- Agent/orchestrator interfaces
- Theme system
- Installed dependencies
- Docker/build process
- Attached BlockNote source repository

Then create a concise implementation plan based on the actual codebase.

After that, implement the feature in logical stages.

Do not ask me to manually perform routine steps that you can perform yourself within the workspace.

Make sensible architectural decisions based on the existing project.

Avoid unnecessary rewrites.

Use the attached BlockNote source as a technical reference throughout the implementation.

When finished, provide a concise report containing:

- What was implemented
- Architecture used
- Files created
- Files modified
- Dependencies added
- Database changes
- API changes
- BlockNote customizations
- Hermes integration points
- Tests/build checks performed
- Any remaining recommended improvements