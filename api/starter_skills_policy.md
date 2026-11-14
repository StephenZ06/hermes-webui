# Skills and tools policy

<!-- hermes:skills-policy:begin -->
Skills and tools are on demand. Each one costs tokens and time every time it
loads (a skill is often 5 to 30 KB of text that stays in the conversation, and
every tool's description is sent with every request), so use one only when the
task is in its domain.

## Skills

- **Start without them.** Answer from what you know and the project's own
  files. Do not load a skill to open a conversation, to greet, or to answer a
  question, and do not load process skills for a read-only question or a
  one-line change.
- **Load when the task is in the skill's domain**, right before that work, and
  once per conversation (do not reload it; keep what you learned):
  - the user names it;
  - the task is the kind of work the skill's description says it covers (UI
    work with a design skill, writing tests with a testing skill, a failing
    test with a debugging skill, a commit message with a commit skill);
  - the project's `AGENTS.md` lists it for that kind of work.
- **Load only what the task needs.** One skill that fits beats three that
  might. Read a skill's extra files only when its steps point to them.
- **Style skills are the exception.** A skill that sets how you reply (a
  terse-style skill, for example) stays on for the whole conversation and is
  not reloaded.

## Tools

- Prefer the cheapest tool that answers the question: search, then read the
  lines you need, before reading whole files.
- Do not open the browser, analyse images or video, generate media, or start a
  sub-agent unless the task needs it. If you can finish in two or three tool
  calls yourself, do not delegate.
- Do not repeat a call whose result is already in the conversation.
- Keep tool output small: filter, limit and paginate instead of dumping.
<!-- hermes:skills-policy:end -->
