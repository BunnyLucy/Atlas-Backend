from dataclasses import dataclass


@dataclass
class AtlasError(Exception):
    status_code: int
    code: str
    message: str
    details: dict | None = None

