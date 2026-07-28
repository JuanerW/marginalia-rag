from benchmark.pipeline import (
    BM25,
    Chunk,
    chunk_chapter,
    fixed_chunks,
    relevance,
)

from src.services.epub_parser import ParsedEpubChapter


def make_chapter(content: str) -> ParsedEpubChapter:
    return ParsedEpubChapter(
        number=1,
        spine_index=0,
        title="第一回 测试",
        content=content,
        source_href="text/chapter1.xhtml",
        fragment_id=None,
        start_offset=0,
        end_offset=len(content),
    )


def test_chunks_preserve_offsets_and_size() -> None:
    content = "\n\n".join(
        [
            "第一段。" * 80,
            "第二段讲述另一件事情。" * 60,
            "第三段作为结尾。" * 50,
        ]
    )
    chunks = chunk_chapter(
        make_chapter(content),
        chapter_number=1,
        target_size=300,
        max_size=400,
        overlap=50,
    )

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.content) <= 400
        assert content[chunk.start_offset : chunk.end_offset] == chunk.content


def test_relevance_requires_most_of_evidence() -> None:
    question = {
        "chapter_number": 1,
        "evidence": [{"start_offset": 100, "end_offset": 200}],
    }
    full = Chunk("full", 1, "第一回", "c1.xhtml", 90, 210, "x" * 120)
    partial = Chunk("partial", 1, "第一回", "c1.xhtml", 150, 250, "x" * 100)
    wrong_chapter = Chunk("wrong", 2, "第二回", "c2.xhtml", 90, 210, "x" * 120)

    assert relevance(question, full) == 2
    assert relevance(question, partial) == 1
    assert relevance(question, wrong_chapter) == 0


def test_entity_relevance_accepts_every_matching_chunk() -> None:
    question = {
        "chapter_number": 1,
        "evidence": [{"start_offset": 0, "end_offset": 10}],
        "relevant_terms": ["张角"],
    }
    later_mention = Chunk(
        "later",
        1,
        "第一回",
        "c1.xhtml",
        500,
        520,
        "众人又谈起张角。",
    )

    assert relevance(question, later_mention) == 2


def test_fixed_chunks_preserve_offsets_and_overlap() -> None:
    content = "天地玄黄" * 300
    chunks = fixed_chunks(
        make_chapter(content),
        chapter_number=1,
        size=400,
        overlap=50,
    )

    assert len(chunks) == 4
    assert chunks[1].start_offset == 350
    for chunk in chunks:
        assert content[chunk.start_offset : chunk.end_offset] == chunk.content


def test_bm25_prefers_matching_document() -> None:
    bm25 = BM25(["桃园结义刘备关羽张飞", "董卓进入洛阳"])
    scores = bm25.scores("谁在桃园结义")
    assert scores[0] > scores[1]
