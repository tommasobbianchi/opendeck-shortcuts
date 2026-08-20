from dataclasses import dataclass
from typing import Literal

Provenance = Literal["extracted", "curated", "guessed"]


@dataclass(frozen=True)
class Shortcut:
    id: str
    app: str
    label: str
    combo: str
    provenance: Provenance
    source: str
    category: str = ""
    icon: str | None = None

    @property
    def tokens(self) -> str:
        from . import keys

        return keys.encode(self.combo)
