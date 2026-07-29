import pytest

from src.services.text_parser import TextDecodeError, decode_txt, split_chapters


def test_decode_utf8_and_normalize_newlines() -> None:
    text, encoding = decode_txt("第一章\r\n你好".encode())
    assert text == "第一章\n你好"
    assert encoding == "utf-8-sig"


def test_decode_gb18030() -> None:
    text, encoding = decode_txt("第一回\n故事开始".encode("gb18030"))
    assert text == "第一回\n故事开始"
    assert encoding == "gb18030"


def test_reject_empty_text() -> None:
    with pytest.raises(TextDecodeError):
        decode_txt(b"  \n")


def test_split_chinese_chapters_and_keep_offsets() -> None:
    text = "书名\n\n第一章 开始\n第一段。\n\n第二章：相遇\n第二段。"
    chapters = split_chapters(text)

    assert [chapter.title for chapter in chapters] == ["卷首", "第一章 开始", "第二章：相遇"]
    assert [chapter.number for chapter in chapters] == [1, 2, 3]
    for chapter in chapters:
        assert text[chapter.start_offset : chapter.end_offset] == chapter.content


def test_fallback_to_single_chapter() -> None:
    chapters = split_chapters("这是一篇没有章节标题的短篇。")
    assert len(chapters) == 1
    assert chapters[0].title == "正文"
