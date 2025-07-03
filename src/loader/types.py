from dataclasses import dataclass
from pathlib import Path

@dataclass
class LoadedPDF:
    """
    Represents a loaded PDF document with its metadata.
    """

    name: str
    path: Path
    raw_bytes: bytes
