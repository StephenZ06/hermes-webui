# Shared secrets for every profile

By default each Hermes profile keeps its API keys in its own `.env`
(`~/.hermes/.env` for the default profile, `~/.hermes/profiles/<name>/.env`
for the others), and no profile can see another's. When one person uses every
profile, that means the same keys copied into many files. The shared secrets
file replaces those copies with one file.

## How it works

- **One file:** `~/.hermes/shared/secrets.env` (folder `700`, file `600`),
  ordinary `KEY=value` lines.
- **Profiles read it first; their own `.env` wins.** A key set in a profile's
  `.env` overrides the shared value for that profile only.
- **The agent** reads it through the built-in `command` secret source, added
  to each profile's `config.yaml`:

  ```yaml
  secrets:
    command:
      enabled: true
      command: cat /home/<you>/.hermes/shared/secrets.env
      override_existing: false
  ```

- **The WebUI** layers the same file in one place, `api/shared_env.py`, used
  by every reader of profile env (agent runs, provider status, onboarding,
  model lists, TTS, Job OS, ...).
- **Saving a key in the WebUI** (Settings → Providers, onboarding, Jobs →
  Connect Gmail) writes the shared file, unless the active profile already
  overrides that key in its own `.env`. Removing a key removes it from both.
- **Opt-in:** none of this happens until `shared/secrets.env` exists. Without
  it, every read and write uses the profile `.env` exactly as before.
- **Isolated-profile deployments** (`HERMES_WEBUI_ISOLATED_PROFILE`, one
  contained profile per user) ignore the shared file entirely.

## Trade-off

Profiles stop being secret boundaries for anything in the shared file: every
profile can use every shared key. Put a key that must stay with one profile
in that profile's own `.env` instead.

## Setting it up

1. Back up every profile `.env` and `config.yaml`.
2. Create `~/.hermes/shared/` (`chmod 700`) and `secrets.env` (`chmod 600`)
   with the keys common to all profiles. If two profiles hold different
   values for the same key, keep the odd one out in that profile's `.env`.
3. Add the `secrets.command` block above to every profile's `config.yaml`
   (including `~/.hermes/config.yaml`).
4. Remove the now-shared lines from each profile `.env`.
5. Restart the WebUI (`systemctl --user restart hermes-webui-native.service`
   for the native install).
6. Check that every profile still resolves every key it had before, with the
   same value — compare hashes, not values.

To undo: copy the backed-up `.env` and `config.yaml` files back, delete
`~/.hermes/shared/secrets.env`, and restart.
