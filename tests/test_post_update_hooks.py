"""Post-update hooks: user scripts that re-apply local work after an update.

`apply_update()` and `apply_force_update()` both move a target repo onto the
remote ref -- the force path does a literal `git reset --hard`, which silently
destroys any local commit the user carries on top of upstream. That is the
right default for an updater, but it leaves no seam for a local customisation
that has to survive updates (a custom tool module in the agent's `tools/`
directory being the motivating case).

These tests pin the seam: executable scripts in `$HERMES_HOME/post-update.d/`
run after the repo has been moved and BEFORE the gateway/server restart, so a
restored file is present when the new process imports its tool modules.

The runner is deliberately fail-soft. A broken hook must never turn a
successful update into a failed one -- the update already happened by the time
hooks run, so raising would only strand the user between states.
"""
import os
import stat
import subprocess

import pytest

import api.updates as updates


def _write_hook(directory, name, body, *, executable=True):
    directory.mkdir(parents=True, exist_ok=True)
    hook = directory / name
    hook.write_text(body, encoding='utf-8')
    if executable:
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    return hook


@pytest.fixture
def hook_home(tmp_path, monkeypatch):
    """An isolated HERMES_HOME whose post-update.d the runner will read."""
    home = tmp_path / 'hermes-home'
    home.mkdir()
    monkeypatch.setenv('HERMES_HOME', str(home))
    return home


def test_hooks_run_in_sorted_order_with_target_and_repo(hook_home, tmp_path):
    """Hooks fire in filename order and receive the target name and repo path.

    Ordering is by filename so users can sequence with the usual `10-`, `20-`
    prefixes; both argv and the environment carry the context so a hook can be
    a one-line shell script without argument parsing.
    """
    repo = tmp_path / 'agent-repo'
    repo.mkdir()
    log = tmp_path / 'hook.log'
    hooks = hook_home / 'post-update.d'
    _write_hook(
        hooks, '20-second.sh',
        f'#!/bin/sh\necho "second $1 $2 $HERMES_UPDATE_TARGET" >> {log}\n',
    )
    _write_hook(
        hooks, '10-first.sh',
        f'#!/bin/sh\necho "first $1 $2 $HERMES_UPDATE_REPO" >> {log}\n',
    )

    results = updates._run_post_update_hooks('agent', repo)

    lines = log.read_text(encoding='utf-8').splitlines()
    assert lines == [
        f'first agent {repo} {repo}',
        f'second agent {repo} agent',
    ]
    assert [r['hook'] for r in results] == ['10-first.sh', '20-second.sh']
    assert all(r['ok'] for r in results)


def test_non_executable_and_dotfiles_are_skipped(hook_home, tmp_path):
    """Only executable, non-hidden regular files count as hooks.

    A dropped-in `.bak` or an editor's dotfile must not be executed, and a
    non-executable script is treated as deliberately parked rather than run
    through a shell we picked for the user.
    """
    repo = tmp_path / 'agent-repo'
    repo.mkdir()
    log = tmp_path / 'hook.log'
    hooks = hook_home / 'post-update.d'
    _write_hook(hooks, '10-live.sh', f'#!/bin/sh\necho live >> {log}\n')
    _write_hook(
        hooks, '20-parked.sh', f'#!/bin/sh\necho parked >> {log}\n',
        executable=False,
    )
    _write_hook(hooks, '.30-hidden.sh', f'#!/bin/sh\necho hidden >> {log}\n')
    (hooks / 'subdir').mkdir()

    results = updates._run_post_update_hooks('agent', repo)

    assert log.read_text(encoding='utf-8').splitlines() == ['live']
    assert [r['hook'] for r in results] == ['10-live.sh']


def test_missing_hook_dir_is_a_silent_no_op(hook_home, tmp_path):
    """No `post-update.d` is the normal case and must not warn or raise."""
    repo = tmp_path / 'agent-repo'
    repo.mkdir()

    assert updates._run_post_update_hooks('agent', repo) == []


def test_failing_hook_is_reported_but_not_fatal(hook_home, tmp_path):
    """A non-zero hook is recorded as failed; later hooks still run.

    The update itself has already been applied when hooks run, so one broken
    script must not abort the rest or propagate an exception into the caller.
    """
    repo = tmp_path / 'agent-repo'
    repo.mkdir()
    log = tmp_path / 'hook.log'
    hooks = hook_home / 'post-update.d'
    _write_hook(hooks, '10-broken.sh', '#!/bin/sh\necho boom >&2\nexit 3\n')
    _write_hook(hooks, '20-after.sh', f'#!/bin/sh\necho after >> {log}\n')

    results = updates._run_post_update_hooks('agent', repo)

    assert [(r['hook'], r['ok'], r['status']) for r in results] == [
        ('10-broken.sh', False, 'failed'),
        ('20-after.sh', True, 'ok'),
    ]
    assert log.read_text(encoding='utf-8').splitlines() == ['after']


def test_hook_timeout_is_bounded_and_reported(hook_home, tmp_path, monkeypatch):
    """A hanging hook is killed rather than stalling the update indefinitely."""
    repo = tmp_path / 'agent-repo'
    repo.mkdir()
    hooks = hook_home / 'post-update.d'
    _write_hook(hooks, '10-hang.sh', '#!/bin/sh\nsleep 30\n')
    monkeypatch.setattr(updates, '_POST_UPDATE_HOOK_TIMEOUT_SECONDS', 1)

    results = updates._run_post_update_hooks('agent', repo)

    assert [(r['hook'], r['ok'], r['status']) for r in results] == [
        ('10-hang.sh', False, 'timeout'),
    ]


def test_hook_stderr_is_captured_not_inherited(hook_home, tmp_path):
    """Hook output is captured so it lands in the log, not the server stdout."""
    repo = tmp_path / 'agent-repo'
    repo.mkdir()
    hooks = hook_home / 'post-update.d'
    _write_hook(hooks, '10-noisy.sh', '#!/bin/sh\necho to-stdout\necho to-stderr >&2\n')

    results = updates._run_post_update_hooks('agent', repo)

    assert results[0]['ok'] is True
    assert 'to-stdout' in results[0]['output']
    assert 'to-stderr' in results[0]['output']


def test_hooks_run_before_every_restart_in_the_apply_paths():
    """Every successful apply path runs hooks before it restarts anything.

    A hook that restores a file the agent imports is useless if the process
    that reads it has already been re-execed. Rather than mock the whole git
    surface of three separate success paths, assert the ordering structurally:
    in `api/updates.py`, each `_ensure_gateway_restart_for_agent_update()` and
    each `_schedule_restart()` call must be preceded by a hook run.
    """
    source = (updates.__file__ and open(updates.__file__, encoding='utf-8').read()) or ''
    lines = source.splitlines()

    hook_lines = [
        i for i, line in enumerate(lines)
        if '_run_post_update_hooks(' in line and 'def ' not in line
    ]
    restart_lines = [
        i for i, line in enumerate(lines)
        if ('_ensure_gateway_restart_for_agent_update()' in line
            or '_schedule_restart()' in line)
        and 'def ' not in line
    ]

    assert hook_lines, 'no _run_post_update_hooks() call sites found'
    assert restart_lines, 'no restart call sites found'
    for restart_line in restart_lines:
        assert any(h < restart_line for h in hook_lines), (
            f'restart at api/updates.py:{restart_line + 1} is not preceded by '
            'a _run_post_update_hooks() call'
        )
