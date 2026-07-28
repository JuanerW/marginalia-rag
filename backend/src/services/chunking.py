import re
from dataclasses import dataclass

BODY_SEPARATOR = "--------------------"
SENTENCE_PATTERN = re.compile(r".*?[。！？!?；;](?:[”’」』])?|.+$", re.DOTALL)


@dataclass(frozen=True)
class TextChunk:
    start_offset: int
    end_offset: int
    content: str


@dataclass(frozen=True)
class Segment:
    start: int
    end: int


def _body_end(content: str) -> int:
    position = content.find(BODY_SEPARATOR)
    return position if position >= 0 else len(content)


def _segments(content: str, max_size: int) -> list[Segment]:
    body = content[: _body_end(content)]
    segments: list[Segment] = []
    for match in re.finditer(r"\S(?:.*?\S)?(?=\n{2,}|\Z)", body, re.DOTALL):
        start, end = match.span()
        if end - start <= max_size:
            segments.append(Segment(start, end))
            continue
        paragraph = content[start:end]
        for sentence in SENTENCE_PATTERN.finditer(paragraph):
            sentence_start = start + sentence.start()
            sentence_end = start + sentence.end()
            while sentence_end - sentence_start > max_size:
                segments.append(
                    Segment(sentence_start, sentence_start + max_size)
                )
                sentence_start += max_size
            if sentence_start < sentence_end:
                segments.append(Segment(sentence_start, sentence_end))
    return segments


def chunk_text(
    content: str,
    target_size: int = 700,
    max_size: int = 900,
    overlap: int = 100,
) -> list[TextChunk]:
    if not 0 <= overlap < target_size <= max_size:
        raise ValueError("Chunk 参数必须满足 0 <= overlap < target_size <= max_size")
    segments = _segments(content, max_size)
    chunks: list[TextChunk] = []
    start_index = 0
    while start_index < len(segments):
        end_index = start_index
        while end_index + 1 < len(segments):
            proposed = segments[end_index + 1].end - segments[start_index].start
            if proposed > max_size:
                break
            end_index += 1
            if segments[end_index].end - segments[start_index].start >= target_size:
                break

        start = segments[start_index].start
        end = segments[end_index].end
        chunks.append(TextChunk(start, end, content[start:end]))
        if end_index == len(segments) - 1:
            break
        overlap_index = end_index
        while (
            overlap_index > start_index
            and end - segments[overlap_index - 1].start <= overlap
        ):
            overlap_index -= 1
        start_index = max(start_index + 1, overlap_index)
    return chunks
