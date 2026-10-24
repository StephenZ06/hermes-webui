"""In-process cron ticker for single-container Docker deployments.

docker-compose.yml runs the agent in-process with no separate ``hermes
gateway`` daemon (see docs/docker.md #scheduled-jobs-and-the-gateway-daemon).
Without a daemon, scheduled cron jobs never fire on their own and
``gateway_state.json`` goes stale, so the Scheduled Jobs page shows "Gateway
metadata stale". This thread fills the daemon's two jobs directly: tick every
profile's cron store every 60s, and refresh ``gateway_state.json`` so
agent_health.py's cross-container freshness check reads "alive".
"""
import logging
import threading

logger = logging.getLogger(__name__)

_TICK_INTERVAL_S = 60
_stop_event: threading.Event | None = None


def _iter_profile_homes():
    from api.profiles import _DEFAULT_HERMES_HOME, _profiles_root

    homes = [_DEFAULT_HERMES_HOME]
    root = _profiles_root()
    if root.is_dir():
        # config.yaml is the marker of a real profile -- without this check,
        # ticking (and thus continuously refreshing gateway_state.json in)
        # an orphaned directory left behind by a deleted profile makes it
        # look perpetually "alive" and never lets it disappear from the
        # profile list on its own.
        homes.extend(
            sorted(p for p in root.iterdir() if p.is_dir() and (p / "config.yaml").exists())
        )
    return homes


def _tick_and_heartbeat_all_profiles() -> None:
    from api.routes import _ensure_agent_cron_import_path
    from api.profiles import cron_profile_context_for_home

    _ensure_agent_cron_import_path()
    from cron.scheduler import tick as cron_tick
    from gateway.status import write_runtime_status

    for home in _iter_profile_homes():
        try:
            with cron_profile_context_for_home(home):
                # sync=True: due jobs run before this profile's context
                # exits. A handed-off run (sync=False) checked its fire claim
                # after the context had moved to the next profile, read the
                # wrong jobs.json, and was dropped every time.
                cron_tick(verbose=False, sync=True)
                write_runtime_status(gateway_state="running")
        except ModuleNotFoundError:
            # Agent's cron/gateway packages not on the import path at all —
            # nothing to tick anywhere, stop trying every profile.
            raise
        except Exception as e:
            logger.warning("gateway_ticker: tick failed for profile home %s: %s", home, e)


def _loop(stop_event: threading.Event) -> None:
    try:
        _tick_and_heartbeat_all_profiles()
    except ModuleNotFoundError as e:
        logger.info("gateway_ticker: cron package unavailable (%s); ticker exiting", e)
        return
    while not stop_event.wait(_TICK_INTERVAL_S):
        try:
            _tick_and_heartbeat_all_profiles()
        except ModuleNotFoundError:
            return
        except Exception as e:
            logger.error("gateway_ticker: tick loop error: %s", e)


def start_gateway_ticker() -> None:
    """Start the in-process cron ticker thread. Idempotent."""
    global _stop_event
    if _stop_event is not None:
        return
    _stop_event = threading.Event()
    threading.Thread(target=_loop, args=(_stop_event,), name="gateway-ticker", daemon=True).start()
