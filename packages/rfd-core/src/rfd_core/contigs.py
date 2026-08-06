"""Contig grammar: parsing, segment classification, and post-normalisation Ls.

Grammar and behaviour transcribed from reference/diffusion.py lines 251-262 and
cross-checked against ColabDesign's fix_contig/fix_partial_contigs/get_Ls at the
pinned commit (e31a56fe1d9b4de25c8697f3a28b75892941cc72). See
aidlc-docs/construction/u2a-core-domain/functional-design/business-logic-model.md
section 1 for the full specification this implements.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


class ContigParseError(ValueError):
    """Raised when a contig segment does not match the grammar.

    Carries the offending raw segment text and a human-readable reason, so a
    caller (e.g. the web form's validator) can point at exactly what was wrong.
    """

    def __init__(self, segment: str, reason: str) -> None:
        self.segment = segment
        self.reason = reason
        super().__init__(f"invalid contig segment {segment!r}: {reason}")


@dataclass(frozen=True)
class Segment:
    """One '/'-separated piece of a contig token.

    Fixed segments reference a template chain (``chain`` set, ``length_*`` unset).
    Free segments specify a length or length range to diffuse (``chain`` unset).
    """

    raw: str
    is_fixed: bool
    chain: Optional[str] = None
    length_min: Optional[int] = None
    length_max: Optional[int] = None


def _parse_segment(seg_raw: str) -> Segment:
    if seg_raw == "":
        raise ContigParseError(seg_raw, "empty segment")

    a = seg_raw.split("-")[0]

    if a == "":
        # e.g. "-40": no chain letter and no valid numeric start.
        raise ContigParseError(seg_raw, "segment starts with '-' or is otherwise malformed")

    if a[0].isalpha():
        # Fixed segment. Full range resolution needs a parsed template PDB and
        # happens in rfd-runner (ContigNormaliser, U2b) via ColabDesign's
        # fix_contigs/fix_partial_contigs -- rfd-core only extracts the chain
        # letter, which is all mode inference and fixed_chains need.
        return Segment(raw=seg_raw, is_fixed=True, chain=a[0])

    if a.isnumeric():
        if a == "0":
            # Deliberate deviation from the notebook (NFR-9): ColabDesign's
            # fix_contig silently DROPS a bare "0" segment (its condition is
            # `x.isnumeric() and x != "0"`). We reject it instead -- this also
            # covers a "0-N" range, since a range's lower bound uses the same
            # leading-token check, preventing RFdiffusion from ever receiving a
            # sampled zero-length insert.
            raise ContigParseError(
                seg_raw,
                "length-0 segments are not allowed (silently dropped by "
                "RFdiffusion upstream; rejected here instead of reproducing "
                "that silent behaviour)",
            )
        if "-" in seg_raw:
            parts = seg_raw.split("-")
            if len(parts) != 2 or not parts[1].isnumeric():
                raise ContigParseError(seg_raw, "malformed length range")
            lo, hi = int(parts[0]), int(parts[1])
            if hi < lo:
                raise ContigParseError(seg_raw, "range upper bound is less than lower bound")
            return Segment(raw=seg_raw, is_fixed=False, length_min=lo, length_max=hi)
        n = int(a)
        return Segment(raw=seg_raw, is_fixed=False, length_min=n, length_max=n)

    raise ContigParseError(seg_raw, "segment is neither a chain reference nor a numeric length")


@dataclass(frozen=True)
class ContigSpec:
    """A parsed contig string: chain tokens, each a list of segments."""

    tokens: List[List[Segment]]

    @classmethod
    def parse(cls, raw: str) -> ContigSpec:
        # Notebook line 251: contigs.replace(","," ").replace(":"," ").split()
        text = raw.replace(",", " ").replace(":", " ")
        raw_tokens = text.split()
        tokens = [[_parse_segment(s) for s in tok.split("/")] for tok in raw_tokens]
        return cls(tokens=tokens)

    @property
    def is_empty(self) -> bool:
        return len(self.tokens) == 0

    @property
    def has_free(self) -> bool:
        return any(not seg.is_fixed for segs in self.tokens for seg in segs)

    @property
    def has_fixed(self) -> bool:
        return any(seg.is_fixed for segs in self.tokens for seg in segs)

    @property
    def fixed_chains(self) -> List[str]:
        seen: List[str] = []
        for segs in self.tokens:
            for seg in segs:
                if seg.is_fixed and seg.chain not in seen:
                    seen.append(seg.chain)  # type: ignore[arg-type]
        return seen

    def to_list(self) -> List[str]:
        return ["/".join(seg.raw for seg in segs) for segs in self.tokens]


def get_Ls(normalised_contigs: List[str]) -> List[int]:
    """Per-chain residue counts from ALREADY-NORMALISED contigs.

    Transcribed exactly from ColabDesign's get_Ls. Unlike ContigSpec.parse,
    this expects the output of rfd-runner's ContigNormaliser: every '/'-part
    has exactly one dash (e.g. "A163-181" or "40-40"), never a bare length or
    an open-ended range. Used for chain-length colouring (FR-22, U4).
    """
    Ls: List[int] = []
    for contig in normalised_contigs:
        total = 0
        for part in contig.split("/"):
            a, b = part.split("-")
            if a[0].isalpha():
                total += int(b) - int(a[1:]) + 1
            else:
                total += int(b)
        Ls.append(total)
    return Ls
