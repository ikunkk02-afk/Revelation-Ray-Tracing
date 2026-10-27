"""Digest shader source, metadata and lookup assets to reject stale reports."""
import hashlib
from pathlib import Path
SHADERS=Path(__file__).resolve().parents[1]/'shaders'
def source_digest():
    digest=hashlib.sha256()
    # Preserve the original Windows ordering on Linux release builders too.
    for p in sorted((p for p in SHADERS.rglob('*') if p.is_file()),
                    key=lambda p: tuple(s.casefold() for s in p.relative_to(SHADERS).parts)):
        digest.update(p.relative_to(SHADERS).as_posix().encode())
        digest.update(b'\0')
        digest.update(hashlib.sha256(p.read_bytes()).digest())
    return digest.hexdigest()
