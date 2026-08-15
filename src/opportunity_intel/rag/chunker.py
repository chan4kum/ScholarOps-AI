"""Structure-Aware Semantic Document Chunker for ScholarOps AI.

Splits academic documents, CVs, and proposals into cohesive semantic chunks based on:
1. Markdown headers (# H1, ## H2, ### H3) and section boundaries.
2. Paragraph and bullet list groupings.
3. Configurable token/character window limits with semantic sliding overlap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SemanticChunk:
    id: str
    text: str
    section_title: str = ""
    start_char: int = 0
    end_char: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


class StructureAwareChunker:
    """Chunks documents while preserving structural hierarchy and semantic coherence."""

    def __init__(
        self,
        max_chunk_size: int = 800,
        min_chunk_size: int = 100,
        overlap_size: int = 150,
    ) -> None:
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap_size = overlap_size

    def chunk_document(
        self,
        doc_id: str | int,
        text: str,
        *,
        base_metadata: dict[str, object] | None = None,
    ) -> list[SemanticChunk]:
        """Splits document text into structure-aware semantic chunks."""
        if not text or not text.strip():
            return []

        base_meta = dict(base_metadata or {})
        sections = self._split_into_sections(text)
        chunks: list[SemanticChunk] = []
        global_chunk_idx = 0

        for section_title, section_body in sections:
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", section_body) if p.strip()]
            current_buffer: list[str] = []
            current_len = 0

            for para in paragraphs:
                para_len = len(para)
                if current_len + para_len > self.max_chunk_size and current_buffer:
                    chunk_text = "\n\n".join(current_buffer)
                    if section_title and not chunk_text.startswith(f"## {section_title}"):
                        chunk_text = f"Section: {section_title}\n{chunk_text}"

                    meta = {
                        **base_meta,
                        "doc_id": doc_id,
                        "section": section_title,
                        "chunk_idx": global_chunk_idx,
                    }
                    chunks.append(
                        SemanticChunk(
                            id=f"doc-{doc_id}-chunk-{global_chunk_idx}",
                            text=chunk_text,
                            section_title=section_title,
                            metadata=meta,
                        )
                    )
                    global_chunk_idx += 1

                    # Apply overlap from end of previous buffer
                    has_overlap = len(chunk_text) > self.overlap_size
                    overlap_chars = chunk_text[-self.overlap_size :] if has_overlap else ""
                    current_buffer = [overlap_chars, para] if overlap_chars else [para]
                    current_len = sum(len(c) for c in current_buffer)
                else:
                    current_buffer.append(para)
                    current_len += para_len

            if current_buffer:
                chunk_text = "\n\n".join(current_buffer).strip()
                if len(chunk_text) >= self.min_chunk_size or not chunks:
                    if section_title and not chunk_text.startswith(f"Section: {section_title}"):
                        chunk_text = f"Section: {section_title}\n{chunk_text}"

                    meta = {
                        **base_meta,
                        "doc_id": doc_id,
                        "section": section_title,
                        "chunk_idx": global_chunk_idx,
                    }
                    chunks.append(
                        SemanticChunk(
                            id=f"doc-{doc_id}-chunk-{global_chunk_idx}",
                            text=chunk_text,
                            section_title=section_title,
                            metadata=meta,
                        )
                    )
                    global_chunk_idx += 1

        return chunks

    def _split_into_sections(self, text: str) -> list[tuple[str, str]]:
        """Identifies markdown headers or academic section dividers."""
        header_pattern = re.compile(r"(?m)^(#{1,4}\s+[^\n]+|[A-Z][A-Za-z\s]{3,40}:)")
        matches = list(header_pattern.finditer(text))

        if not matches:
            return [("General Content", text)]

        sections: list[tuple[str, str]] = []
        # Leading text before first header
        if matches[0].start() > 0:
            leading = text[: matches[0].start()].strip()
            if leading:
                sections.append(("Introduction / Header", leading))

        for i, match in enumerate(matches):
            title = match.group(0).strip("#: ").strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                sections.append((title, body))

        return sections if sections else [("General Content", text)]
