"""Chunked page-range parsing. The pipeline never processes the book at once:
every stage takes an explicit page range (chunk) so memory stays bounded and
any stage can be re-run on any subset."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    start: int
    end: int  # inclusive

    @property
    def pages(self):
        return range(self.start, self.end + 1)

    def __contains__(self, page: int) -> bool:
        return self.start <= page <= self.end

    def __str__(self) -> str:
        if self.start == self.end:
            return str(self.start)
        return f"{self.start}-{self.end}"


def parse_range(spec: str, total: int | None = None) -> list[Chunk]:
    """Parse '1-20', '1,5,9', '1-10,15-18' into a list of Chunks."""
    chunks = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = int(a), int(b)
        else:
            a = b = int(part)
        if a < 1 or b < a:
            raise ValueError(f"bad page range: {part!r}")
        if total is not None and b > total:
            raise ValueError(f"page range {part} exceeds total pages ({total})")
        chunks.append(Chunk(a, b))
    if not chunks:
        raise ValueError("empty page range")
    return chunks
