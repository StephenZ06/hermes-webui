"""Provider catalogue and capability registry.

``adapter`` providers can be connected today. ``planned`` providers are shown
so the owner can see the road ahead, and expose no capability at all: a card
for a service that does nothing yet must not look connectable.

Scopes and endpoints were checked against provider documentation on
2026-11-04 (see the design doc). Publishing capabilities for Threads and
Instagram are deliberately absent until that phase is approved.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

READ = "read"
INTERNAL_WRITE = "internal_write"
EXTERNAL_WRITE = "external_write"
CRITICAL = "critical"

AUTOMATIC = "automatic"
APPROVAL = "approval"
DISABLED = "disabled"
MODES = (AUTOMATIC, APPROVAL, DISABLED)

AGENTS = ("conductor", "email", "marketing", "operations", "documents")
FLOORS = ("email", "marketing", "operations", "documents")

GMAIL_READ = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_COMPOSE = "https://www.googleapis.com/auth/gmail.compose"


@dataclass(frozen=True)
class Field:
    kind: str = "string"
    required: bool = False
    max_length: int = 2000


@dataclass(frozen=True)
class Capability:
    id: str
    provider: str
    label: str
    description: str
    risk: str
    fields: dict[str, Field] = field(default_factory=dict)
    scopes: tuple[str, ...] = ()
    idempotent: bool = False

    @property
    def requires_approval(self) -> bool:
        return self.risk in (EXTERNAL_WRITE, CRITICAL)


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    floor: str
    purpose: str
    pricing: str
    auth: str  # oauth | vault | none
    state: str  # adapter | planned
    phase: str = ""
    oauth_app: str = ""


PROVIDERS: tuple[Provider, ...] = (
    Provider("gmail", "Gmail", "email", "Search, read and draft business email.", "Free with a Google account", "oauth", "adapter", "Now", "google"),
    Provider("chatwoot", "Chatwoot", "email", "Shared support inbox and live chat.", "Open source, self-hosted", "none", "planned", "Later"),
    Provider("threads", "Threads", "marketing", "Account sign-in. Posting arrives in a later phase.", "Free API", "oauth", "adapter", "Now", "threads"),
    Provider("instagram", "Instagram", "marketing", "Professional account sign-in. Posting arrives in a later phase.", "Free API", "oauth", "adapter", "Now", "instagram"),
    Provider("listmonk", "Listmonk", "marketing", "Opt-in lists and newsletters.", "Open source, self-hosted", "none", "planned", "Later"),
    Provider("mautic", "Mautic", "marketing", "Advanced campaign management.", "Open source, self-hosted", "none", "planned", "Optional"),
    Provider("google_calendar", "Google Calendar", "operations", "Meetings, reminders and deadlines.", "Free with a Google account", "none", "planned", "Later"),
    Provider("twenty", "Twenty CRM", "operations", "Contacts, leads and pipelines.", "Open source, self-hosted", "none", "planned", "Later"),
    Provider("erpnext", "ERPNext", "operations", "Inventory, suppliers and purchasing.", "Open source, self-hosted", "none", "planned", "Later"),
    Provider("plane", "Plane", "operations", "Issues and roadmaps.", "Open source, self-hosted", "none", "planned", "Optional"),
    Provider("obsidian", "Obsidian vault", "documents", "Notes in folders you grant to this business.", "Your existing vault", "vault", "adapter", "Now"),
    Provider("google_drive", "Google Drive", "documents", "Shared cloud documents.", "Free with a Google account", "none", "planned", "Optional"),
    Provider("paperless", "Paperless-ngx", "documents", "Searchable invoices and receipts.", "Open source, self-hosted", "none", "planned", "Later"),
    Provider("nas", "NAS", "documents", "Allow-listed local file storage.", "Your existing storage", "none", "planned", "Optional"),
)

_S = Field
CAPABILITIES: tuple[Capability, ...] = (
    Capability("gmail.search_messages", "gmail", "Search mail", "Find messages with a Gmail search query.", READ,
               {"query": _S(required=True, max_length=500), "limit": _S("integer")}, (GMAIL_READ,), True),
    Capability("gmail.read_message", "gmail", "Read a message", "Read one message.", READ,
               {"message_id": _S(required=True, max_length=200)}, (GMAIL_READ,), True),
    Capability("gmail.get_thread", "gmail", "Read a thread", "Read a whole conversation.", READ,
               {"thread_id": _S(required=True, max_length=200)}, (GMAIL_READ,), True),
    Capability("gmail.create_draft", "gmail", "Create a draft", "Save a draft in the mailbox. Nothing is sent.", INTERNAL_WRITE,
               {"to": _S(required=True, max_length=500), "subject": _S(required=True, max_length=500),
                "body": _S(required=True, max_length=100_000), "thread_id": _S(max_length=200)}, (GMAIL_COMPOSE,)),
    Capability("gmail.send_draft", "gmail", "Send a draft", "Send a saved draft after you approve it.", EXTERNAL_WRITE,
               {"draft_id": _S(required=True, max_length=200)}, (GMAIL_COMPOSE,)),
    Capability("threads.get_profile", "threads", "Read profile", "Read the signed-in Threads profile.", READ, {}, ("threads_basic",), True),
    Capability("instagram.get_profile", "instagram", "Read profile", "Read the signed-in Instagram profile.", READ, {}, ("instagram_business_basic",), True),
    Capability("obsidian.search_notes", "obsidian", "Search notes", "Search granted folders.", READ,
               {"query": _S(required=True, max_length=500), "limit": _S("integer")}, (), True),
    Capability("obsidian.read_note", "obsidian", "Read a note", "Read a note in a granted folder.", READ,
               {"path": _S(required=True, max_length=1000)}, (), True),
    Capability("obsidian.create_note", "obsidian", "Create a note", "Create a new note in a granted folder.", INTERNAL_WRITE,
               {"folder": _S(required=True, max_length=1000), "title": _S(required=True, max_length=200),
                "body": _S(required=True, max_length=1_000_000)}),
    Capability("obsidian.edit_note", "obsidian", "Edit a note", "Replace text in a note, keeping everything else.", INTERNAL_WRITE,
               {"path": _S(required=True, max_length=1000), "expected_revision": _S(required=True, max_length=64),
                "find": _S(required=True, max_length=200_000), "replace": _S(required=True, max_length=1_000_000)}),
)

_PROVIDER_INDEX = {provider.id: provider for provider in PROVIDERS}
_CAPABILITY_INDEX = {capability.id: capability for capability in CAPABILITIES}


def provider(provider_id: str) -> Provider | None:
    return _PROVIDER_INDEX.get(str(provider_id or ""))


def capability(capability_id: str) -> Capability | None:
    return _CAPABILITY_INDEX.get(str(capability_id or ""))


def provider_capabilities(provider_id: str) -> list[Capability]:
    return [item for item in CAPABILITIES if item.provider == provider_id]


def default_mode(agent_id: str, item: Capability) -> str:
    """The mode a capability has before the owner changes it.

    Only the agent of the provider's own floor gets anything: a grant never
    leaks sideways by default. External writes need approval and critical
    actions stay off.
    """
    owner = _PROVIDER_INDEX[item.provider].floor
    if agent_id != owner or item.risk == CRITICAL:
        return DISABLED
    return APPROVAL if item.risk == EXTERNAL_WRITE else AUTOMATIC


def allowed_modes(item: Capability) -> tuple[str, ...]:
    if item.risk == CRITICAL:
        return (DISABLED,)
    if item.risk == EXTERNAL_WRITE:
        return (APPROVAL, DISABLED)
    return MODES


def validate_input(item: Capability, raw: Any) -> dict[str, Any]:
    """Check input against the capability's fields; unknown keys are refused."""
    if not isinstance(raw, dict):
        raise ValueError("Input must be an object")
    unknown = sorted(set(raw) - set(item.fields))
    if unknown:
        raise ValueError(f"Unknown input: {', '.join(unknown)}")
    clean: dict[str, Any] = {}
    for name, spec in item.fields.items():
        value = raw.get(name)
        if value is None or value == "":
            if spec.required:
                raise ValueError(f"{name} is required")
            continue
        if spec.kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be a whole number")
        else:
            if not isinstance(value, str):
                raise ValueError(f"{name} must be text")
            if len(value) > spec.max_length:
                raise ValueError(f"{name} is too long")
        clean[name] = value
    return clean


def public_capability(item: Capability, mode: str | None = None) -> dict[str, Any]:
    data = asdict(item)
    data["inputs"] = [{"name": name, "kind": spec.kind, "required": spec.required} for name, spec in item.fields.items()]
    data.pop("fields")
    data["requires_approval"] = item.requires_approval
    data["allowed_modes"] = list(allowed_modes(item))
    if mode is not None:
        data["mode"] = mode
    return data
