from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
DOCKERIGNORE = (ROOT / ".dockerignore").read_text(encoding="utf-8")
SW_JS = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")


def test_compose_passes_a_real_version_into_the_image():
    """Without this, rebuilding the image changes nothing the browser will fetch.

    Every asset URL is `?v=<WEBUI_VERSION>` and the service worker names its
    cache `hermes-shell-<WEBUI_VERSION>`. The Dockerfile defaults that build arg
    to the literal string `unknown`, and `.git` is excluded from the build
    context so the build cannot derive it. A plain `docker compose build` that
    does not pass the arg therefore produces an image whose asset URLs and cache
    name are byte-identical to the previous one, and the browser keeps serving
    the first copy of style.css / *.js it ever cached -- observed live on
    2026-08-31, where the container served new CSS but the PWA did not show it.
    """
    assert "HERMES_VERSION: ${HERMES_VERSION:-unknown}" in COMPOSE, (
        "docker-compose.yml must forward HERMES_VERSION into the build, or every "
        "rebuild ships an image the browser cannot tell apart from the last one"
    )
    assert "ARG HERMES_VERSION=unknown" in DOCKERFILE
    assert "__version__ = '${HERMES_VERSION}'" in DOCKERFILE
    # The reason it cannot be self-derived, spelled out so the coupling is not
    # quietly broken by un-ignoring .git and assuming the build figures it out.
    assert DOCKERIGNORE.splitlines()[0].strip() == ".git"


def test_service_worker_cache_key_is_version_scoped():
    assert "const CACHE_NAME = 'hermes-shell-__WEBUI_VERSION__';" in SW_JS
    assert "const VQ = '?v=__WEBUI_VERSION__';" in SW_JS
    # Old caches must actually be dropped when the name changes, or a real
    # version buys nothing.
    assert "caches.delete(k)" in SW_JS
