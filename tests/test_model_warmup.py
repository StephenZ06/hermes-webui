"""api/model_warmup.py — prewarm the model catalog at boot, off the critical
path, and never let it disturb startup."""
import api.model_warmup as warm


def _reset():
    warm._started = False


def test_start_is_idempotent_and_returns_status():
    _reset()
    assert warm.start_model_warmup() is True
    assert warm.start_model_warmup() is False
    _reset()


def test_warm_forces_a_catalog_rebuild(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api.config.get_available_models",
        lambda **kw: calls.append(kw) or {"groups": []},
    )
    warm._warm()
    assert calls == [{"force_refresh": True}]


def test_warm_swallows_errors(monkeypatch):
    def boom(**kw):
        raise RuntimeError("provider probe failed")

    monkeypatch.setattr("api.config.get_available_models", boom)
    warm._warm()  # must not raise


def test_server_starts_the_warmup():
    src = (warm.__file__).rsplit("/", 2)[0] + "/server.py"
    with open(src, encoding="utf-8") as fh:
        assert "start_model_warmup()" in fh.read()
