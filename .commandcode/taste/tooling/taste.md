# Tooling & Stack

- Uses only OpenAI Codex and OpenCode Go models/providers in hermes-webui — explicitly no Ollama/llama, and no Claude-specific work ("I don't use llama or any of those models, I ONLY use codex or opencode go models"). Confidence: 0.9
- Maintains ~8 named profiles, each pinned to a specific model and role, and expects the same change applied across every profile individually since profiles are isolated. Confidence: 0.75
- Strongly prefers adapting an existing GitHub repo/library over a hand-rolled implementation ("just implement this repo onto our webapp: …", "Use any repo appropriate for motions/animations, as long as it's smooth"), vendored into the project. Confidence: 0.8
- Actively monitors token/context consumption and expects it minimized; repeatedly asks whether a token count is normal and demands fixes to wasteful paths. Confidence: 0.85
- Considered a personal project, so third-party licensing (copyleft etc.) is not treated as a blocker. Confidence: 0.6
- Works with graphify (the code knowledge-graph CLI) in this workspace and expects the agent to use its graph (query / god-nodes / explain) rather than only reading raw files to orient on a codebase ("use it to understand the current state"). Confidence: 0.55
