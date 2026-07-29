from src.services.chunking import chunk_text, fixed_chunk_text


def test_chunk_text_preserves_offsets_and_body_boundary() -> None:
    body = "\n\n".join(
        [
            "第一段。" * 80,
            "第二段。" * 80,
            "第三段。" * 80,
        ]
    )
    content = body + "\n\n--------------------\n\n这里是注释"
    chunks = chunk_text(
        content,
        target_size=250,
        max_size=350,
        overlap=50,
    )

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 350 for chunk in chunks)
    assert all("这里是注释" not in chunk.content for chunk in chunks)
    assert all(
        content[chunk.start_offset : chunk.end_offset] == chunk.content
        for chunk in chunks
    )


def test_chunk_text_rejects_invalid_profile() -> None:
    try:
        chunk_text("正文", target_size=100, max_size=90, overlap=10)
    except ValueError as exc:
        assert "overlap" in str(exc)
    else:
        raise AssertionError("invalid profile should fail")


def test_fixed_chunk_text_preserves_overlap() -> None:
    content = "天地玄黄" * 300
    chunks = fixed_chunk_text(content, size=400, overlap=50)

    assert len(chunks) == 4
    assert chunks[1].start_offset == 350
    assert all(
        content[chunk.start_offset : chunk.end_offset] == chunk.content
        for chunk in chunks
    )
