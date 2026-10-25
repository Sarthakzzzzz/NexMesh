from dataclasses import dataclass
from typing import Literal


ClientMode = Literal["managed_kubernetes", "remote_participant"]
ClientStatus = Literal[
    "PENDING",
    "APPROVED",
    "PROVISIONING",
    "AWAITING_CLIENT_PACKAGE",
    "READY",
    "ONLINE",
    "OFFLINE",
    "DISABLED",
    "REMOVING",
    "REMOVED",
    "REJECTED",
    "FAILED",
    "REVOKED",
]


@dataclass(frozen=True)
class ClientRecord:
    id: str
    display_name: str
    mode: ClientMode
    status: ClientStatus
