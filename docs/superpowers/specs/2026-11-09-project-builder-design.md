# Project builder: catalog, builder wizard, previews, docs check

Date: 2026-11-09
Status: implemented 2026-11-09 (all four parts)

## Goal

Turn the "Create project workspace" wizard into a website / web-app / mobile
builder. The user brings skills and UI libraries (mostly GitHub links); the
WebUI catalogues them with style tags and preview images; the wizard recommends
a look and feel from the business brief, suggests matching skills and
components, records the choices in the project's instruction files, and can
start building version 1 straight away. Project docs stay current through the
existing `AGENTS.md` rules, backed by a cheap end-of-turn check.

## Background: what Hermes already does

Verified in the agent checkout (`~/.hermes/hermes-agent`) on 2026-11-09:

- Every installed skill is listed in the system prompt by name and one-line
  description (`agent/prompt_builder.py: build_skills_system_prompt`); the agent
  opens the full skill when it judges it relevant. There is no hard trigger.
- Trusted projects may carry skills in `.hermes/skills/` or `.agents/skills/`
  (`agent/skill_utils.py: PROJECT_SKILLS_SUBDIRS`).
- `AGENTS.md` (git root down to cwd), `.hermes.md` and `CLAUDE.md` (cwd) are
  injected into every new conversation whose workspace is the project.
- The wizard's `AGENTS.md` (`api/project_starter.py: _agents`) already tells the
  agent to read `.agent/ECC_HANDOFF.md` and `.agent/PROJECT_STATUS.md` first and
  to update handoff, status, tasks and changelog before finishing. Every
  template uses the same function.
- Gap: `adopt_starter_pack` skips files that already exist, so an adopted
  project with its own `AGENTS.md` never receives these rules.
- Today the wizard writes documents, runs the Architecture agent in the
  background to fill them, and can open an empty project conversation
  (`_startProjectChat`). Nothing is built until the user asks.

## Decisions taken in the conversation

- Install globally, show on the Skills page; choose per project in the wizard.
- Libraries are a mix of npm packages, copy-paste component code and links.
- Imports accept any link the user gives; nothing is blocked by licence or
  source. The licence is shown for information only.
- Previews are pictures or short loops (option "a"); live demos are out of scope.
- Libraries are catalogued per component, and components are chosen by the
  style the user wants.
- Style vocabulary approved: Minimal, Elegant, Playful, Bold, Technical,
  Editorial. Hermes drafts tags on import; the user confirms them.
- The style recommendation comes from the business brief.
- A Platform tag covers mobile components; iOS and Android get Look & feel too.
- "Create & start building" sends the first build message automatically.
- End-of-turn docs check: a chip only, never an automatic model call.
- Spacing, alignment and sizing are verified by measuring browser tests.

## Part 1: catalog

### Storage

- Skills: unchanged location and format (`~/.hermes/skills/<category>/<name>/SKILL.md`).
- Libraries: new per-profile folder `HERMES_HOME/libraries/<slug>/`:
  - `LIBRARY.md`: YAML front matter plus free notes.

    ```yaml
    name: Rare UI
    source: https://github.com/swamimalode07/rare-ui
    license: MIT            # informational only
    kind: copy-paste        # npm | copy-paste | link
    frameworks: [react]     # react | vue | svelte | vanilla | swiftui | compose | react-native | flutter
    tailwind: true
    install: ""             # npm command for kind npm; empty otherwise
    needs_details: false    # true until tags are confirmed
    ```

  - `components/<component-slug>.md`: one file per component or animation set.

    ```yaml
    name: Soft fade text
    role: text-effect       # hero | navigation | text-effect | background | cards | forms | transitions | loaders | icons
    style: [minimal, elegant]
    motion: subtle          # none | subtle | expressive
    platform: [web]         # web | ios | android | react-native | flutter
    demo: https://…         # page the preview was captured from, if any
    files: [src/components/soft-fade.tsx]   # copy-paste only: paths inside the source copy
    ```

  - `source/`: the read-only copy of the repository (shallow, no history).
  - `previews/<component-slug>.webp` and optional `<component-slug>.loop.webp`.
- A new module `api/library_catalog.py` owns reading, validating and writing
  this tree. Slugs follow `skill_import.normalize_category` rules. Every path is
  resolved and must stay inside `HERMES_HOME/libraries/`.

### Intake

- Skills "+" menu → **Import** accepts any link. The import form gets a
  "Skill / Library" switch; skill links keep using `skill_import.install_skill`.
- Skill installs: when the Hermes installer's own scan refuses a skill, the form
  shows its reason and an **Install anyway** button (passes the installer's force
  option). The scan is never disabled silently.
- Library links:
  - The repository is fetched shallowly into a staging folder. No install
    scripts, builds or package managers are run.
  - A background job asks Hermes (planner profile, no tools) to read the README,
    `package.json` and file tree, and draft `LIBRARY.md` plus component entries
    with tags. One model call per library.
  - The draft opens in a review form; saving moves it from staging into the
    catalog.
- Pre-installed: anything already in `HERMES_HOME/libraries/` is listed. Entries
  with missing fields get `needs_details: true`, a "Needs details" badge, and a
  **Draft with Hermes** action.

### Skills page

- New "Libraries" tab beside the skills list: library cards, then component
  cards grouped by role, filterable by style, motion and platform. Editing tags
  writes back to the component file.

### Matching (used by the wizard)

1. Hard filters: platform must match the template (web for Website / Web app,
   ios / android / react-native / flutter for mobile); framework must match the
   project's chosen stack; tailwind components drop out when the stack has no
   Tailwind.
2. Ranking: style overlap with the chosen Look & feel, then motion match, then
   the brief as tie-breaker.
3. The top component per role is pre-ticked and marked Recommended.

Skills are matched the same way using their category and description against
the template and brief; skills have no style tags.

## Part 2: builder wizard

### Steps

Website, Web app, iOS, Android:

1. Kind, 2. Location, 3. Template, 4. Brief, 5. Questions (all as today, restyled),
6. **Look & feel**, 7. **Toolkit**, 8. Review & create.

API, CLI, Research, Blank skip step 6; their Toolkit shows skills only.

### Style recommendation

- `_ANALYSIS_PROMPT` in `api/project_starter_agent.py` gains a `"look"` object:
  `{"style": "<one of the six>", "motion": "none|subtle|expressive", "framework": "<one of the framework keys>", "tailwind": true|false, "why": "one sentence tied to the brief"}`.
  The framework and Tailwind values come from the brief and the answers to step 5;
  they are the "project's chosen stack" used by the hard filters, and the user can
  change them on step 7.
  The parser validates both values against the fixed lists and drops the object
  when either is invalid. No extra model call.
- Step 6 opens with the recommendation selected and its reason shown under the
  heading ("Recommended: Elegant · Subtle, because…"). The user can pick any
  style card and motion level. Without a valid recommendation nothing is
  preselected and Next stays disabled until a choice is made.

### Layout

- Wide dialog with two columns: the step on the left, a live **Build summary**
  on the right (template, style, motion, chosen skills and components, number of
  files to create). Narrow widths fold the summary into a bottom bar that
  expands on tap.
- Choice cards are large and visual; toolkit cards show the preview, name,
  library, tags and a tick box, grouped under role headings.
- 8px spacing grid; cards in a row share one size; icons optically centred.
  Existing motion helpers (`MotionUI`, the step slide used today) are reused.

### What gets written

- `docs/UI_UX.md` gains "Look & feel" (style, motion, reason) and "Approved
  components" (name, library, install or copy instructions, link).
- `AGENTS.md` gains "Skills for this project" with trigger rules (for example
  "Before changing UI files, load `ui-skill-1`") and the rules "Use only the
  approved components; ask before adding another" and the existing project-local
  install rule.
- Copy-paste components are copied from `source/` into the project's component
  folder only for the ticked entries.
- The file preview in step 8 shows all of the above before anything is written.

### Create & start building

- Step 8 offers **Create project** (today's behaviour) and **Create & start
  building**.
- The latter waits for the Architecture job, opens the project conversation and
  sends a first message automatically: build version 1 from the brief with the
  approved components, install dependencies inside the project, update the
  handoff docs, and finish with how to open the preview.
- If the Architecture job fails, the conversation still opens, the message is
  not sent, and the failure is shown with a **Send anyway** button.

## Part 3: previews

- On library import, a headless browser (the Playwright already used by the
  test suite, run only by this job) opens each component's demo page, captures a
  16:10 still and, for components with motion other than none, a loop of about
  3 seconds, saved as WebP without sound.
- Fallbacks, in order: the README's first image, then a plain card showing name
  and tags. The user can replace any preview by dropping an image on the card.
- Cards show the still; the loop plays on hover (desktop) or tap (touch). With
  `prefers-reduced-motion` only the still is shown.
- Skills cards show icon, category and description.
- If Playwright is not available in the container, capture is skipped, the
  fallbacks apply and the library card says previews could not be captured.

## Part 4: docs check and adopt fix

- After a turn that wrote or edited files in a project workspace (known from the
  turn's tool calls), the WebUI compares `.agent/ECC_HANDOFF.md`'s modification
  time with the turn start. If it was not updated, a chip "Docs not updated ·
  Update now" appears under the reply. Pressing it sends a short message asking
  for the handoff, status, tasks and changelog updates. No model call happens
  unless the chip is pressed. Read-only turns and non-project workspaces never
  show it.
- `adopt_starter_pack`: when `AGENTS.md` exists, append a section delimited by
  `<!-- hermes:begin -->` / `<!-- hermes:end -->` carrying the read-first,
  install-locally and update-before-finishing rules, unless the markers are
  already present. `rollback_adopted` removes only that delimited section.

## Error handling

- Fetch failure, unreachable link or a repository without readable files: the
  import form shows the reason; nothing is written to the catalog.
- Draft job failure: the library is saved with `needs_details: true` so the user
  can fill tags by hand.
- Malformed front matter in a pre-installed library: listed with a "Needs
  details" badge, never crashes the page.
- Catalog paths that resolve outside `HERMES_HOME/libraries/` are refused.

## Testing

- Unit: front matter parsing and validation, slug and path checks, matching
  filters and ranking (several libraries, several components per role,
  mismatched platform and framework), analysis `look` parsing (valid, invalid,
  missing), adopt section append and rollback, docs-check decision.
- Browser: Look & feel and Toolkit steps at desktop, narrow and mobile widths,
  measuring gaps, card sizes and icon centring; recommendation preselected with
  its reason; summary panel updates; Create & start building sends exactly one
  message; chip appears only after an editing turn.
- Each test is shown failing before its implementation.

## Delivery order

1. Catalog (storage, intake, Skills page Libraries tab, matching).
2. Builder wizard (steps 6–8, analysis `look`, layout, written files, start building).
3. Previews.
4. Docs check and adopt fix.

Each part ships on its own with its tests, deploy and push.

## Out of scope

- Live component demos and generated mock pages.
- Hard enforcement of skill use (hooks).
- Running library code during import.
