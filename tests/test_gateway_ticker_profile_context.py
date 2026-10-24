"""The in-process cron ticker must run each profile's due jobs inside that
profile's context. With sync=False the run happened on a worker thread after
the context had moved on, so its fire-claim check read another profile's
jobs.json and every run was dropped ("fire claim ownership was already lost
before execution")."""
import sys
import types

import api.gateway_ticker as ticker


def test_each_profile_tick_runs_its_jobs_before_leaving_its_context(monkeypatch, tmp_path):
    homes = [tmp_path / "default", tmp_path / "work"]
    active = []
    seen = []

    class Ctx:
        def __init__(self, home):
            self.home = home
        def __enter__(self):
            active.append(self.home)
        def __exit__(self, *exc):
            active.pop()

    def fake_tick(verbose=True, sync=True, **_):
        # A run handed off (sync=False) would execute after __exit__.
        seen.append((active[-1] if active else None, sync))

    monkeypatch.setattr(ticker, "_iter_profile_homes", lambda: homes)
    monkeypatch.setitem(sys.modules, "cron.scheduler", types.SimpleNamespace(tick=fake_tick))
    monkeypatch.setitem(sys.modules, "gateway.status", types.SimpleNamespace(write_runtime_status=lambda **_: None))
    import api.routes, api.profiles
    monkeypatch.setattr(api.routes, "_ensure_agent_cron_import_path", lambda: None)
    monkeypatch.setattr(api.profiles, "cron_profile_context_for_home", Ctx)

    ticker._tick_and_heartbeat_all_profiles()

    assert seen == [(homes[0], True), (homes[1], True)]


def test_a_due_job_run_on_a_pool_thread_does_not_deadlock_the_ticker(monkeypatch, tmp_path):
    # The agent runs each due job on a pool thread while tick() waits. The
    # WebUI's run_job wrapper took the profile lock again on that thread --
    # held by the waiting ticker -- and the job never ran.
    import concurrent.futures
    import os
    import api.profiles as profiles

    home = tmp_path / "default"
    (home / "cron").mkdir(parents=True)
    ran = []
    fake_cs = types.ModuleType("cron.scheduler")
    fake_cs.run_job = lambda job, *a, **k: ran.append(os.environ.get("HERMES_HOME"))

    def fake_tick(verbose=True, sync=True, **_):
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            pool.submit(fake_cs.run_job, {"id": "j1"}).result(timeout=5)

    fake_cs.tick = fake_tick
    monkeypatch.setitem(sys.modules, "cron.scheduler", fake_cs)
    monkeypatch.setitem(sys.modules, "gateway.status", types.SimpleNamespace(write_runtime_status=lambda **_: None))
    import api.routes
    monkeypatch.setattr(api.routes, "_ensure_agent_cron_import_path", lambda: None)
    monkeypatch.setattr(ticker, "_iter_profile_homes", lambda: [home])
    profiles.install_cron_scheduler_profile_isolation()

    ticker._tick_and_heartbeat_all_profiles()

    assert ran == [str(home)]
    assert profiles._cron_ticker_home is None
