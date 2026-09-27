import io
import json
from urllib.parse import urlsplit


class _Handler:
    def __init__(self, body):
        encoded = json.dumps(body).encode()
        self.rfile = io.BytesIO(encoded)
        self.headers = {"Content-Length": str(len(encoded)), "Content-Type": "application/json"}
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, status): self.status = status
    def send_header(self, *_): pass
    def end_headers(self): pass


def _payload(handler):
    return json.loads(handler.wfile.getvalue())


def test_start_rejects_stale_revision_and_cross_project_items(monkeypatch, tmp_path):
    from api import routes, work_hub

    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "alpha"}, {"project_id": "beta"}])
    alpha = work_hub.create_item({"title": "Alpha", "project_id": "alpha"}, None)
    beta = work_hub.create_item({"title": "Beta", "project_id": "beta"}, alpha["revision"])

    stale = _Handler({
        "project_id": "alpha", "goal": "Ship", "item_ids": [alpha["item"]["id"]], "expected_revision": 0,
    })
    routes.handle_post(stale, urlsplit("/api/work_hub/workflows/start"))
    assert stale.status == 409

    cross_project = _Handler({
        "project_id": "alpha", "goal": "Ship", "item_ids": [alpha["item"]["id"], beta["item"]["id"]],
        "expected_revision": beta["revision"],
    })
    routes.handle_post(cross_project, urlsplit("/api/work_hub/workflows/start"))
    assert cross_project.status == 400
    assert "same project" in _payload(cross_project)["error"]


def test_start_returns_durable_run_before_launching_runner(monkeypatch, tmp_path):
    from api import routes, work_hub

    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda: [{"project_id": "alpha"}])
    started = []
    monkeypatch.setattr("api.workflow_runner.start_workflow_runner", lambda workflow_id: started.append(workflow_id))
    item = work_hub.create_item({"title": "Alpha", "project_id": "alpha"}, None)
    handler = _Handler({
        "project_id": "alpha", "goal": "Ship", "item_ids": [item["item"]["id"]], "expected_revision": item["revision"],
        "topology": "sequential",
    })

    routes.handle_post(handler, urlsplit("/api/work_hub/workflows/start"))

    payload = _payload(handler)
    assert handler.status == 200
    assert payload["workflow"]["status"] == "pending"
    assert started == [payload["workflow"]["id"]]
