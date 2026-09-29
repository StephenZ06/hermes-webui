# Dev Workflow

- After code changes, always rebuild + `--force-recreate` the container; a plain restart serves stale code. He asks "do I need to rebuild/restart?" / "give me the rebuild and recreate commands again" constantly. Confidence: 0.85
- Expects the agent to run the deploy itself and then verify live in the running app ("you deploy it mate", "Rebuild and redeploy so I can see it", "Test it in the browser if possible"), not just report that code was written. Confidence: 0.85
- When he says something still looks unchanged, treat it as a deployment/caching problem to chase down rather than re-explaining the fix ("Done, but why don't I see a change"). Confidence: 0.75
- Wants a revert point saved before risky or large changes ("save this state so I can revert back easily"; "don't forget to save this current state incase i wanna revert back"). Confidence: 0.7
- Wants root causes fixed, not symptoms papered over ("Fix the search_files bug, also any other bug that may increase token usage"; "Close all gaps mate"). Confidence: 0.8
- Repeats a full test-suite run before committing and then commits/pushes/merges ("commit and push this", "move master once tests pass"). Confidence: 0.65
- Comfortable with an agent running long background jobs and reporting back, but gets impatient with opaque waits and asks for status ("still running?", "why is it taking so long?", "hurry up man"). Confidence: 0.7
- Expects a saved workspace to act as a root that contains its project folders: a path nested under a saved workspace (e.g. a project folder under a general "MiniPC-Main" workspace) should be trusted/usable without registering each subfolder separately, including when the subdirectory does not yet exist and will be created on demand. Confidence: 0.85
- For multi-part feature or bug-fix requests, wants the agent to analyze the issues first, then fix them one by one and verify completion before finishing. Confidence: 0.8
