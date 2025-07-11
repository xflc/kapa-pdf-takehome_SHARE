from dataclasses import dataclass
from pathlib import Path

@dataclass
class LoadedPDF:
    """
    TBD
    """

    name: str
    path: Path
    raw_bytes: bytes
