import re
from dataclasses import dataclass

MAX_TXT_SIZE = 20 * 1024 * 1024

CHAPTER_PATTERN = re.compile(
    r"(?m)^[ \t]*("
    r"第[零〇一二三四五六七八九十百千万两\d]+[章回节卷部篇]"
    r"(?:[ \t　:：·、.-]+[^\r\n]{0,80})?"
    r"|序章|序言|前言|引子|楔子|后记|尾声|终章"
    r")[ \t]*$"
)


class TextDecodeError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedChapter:
    number: int
    title: str
    content: str
    start_offset: int
    end_offset: int


def decode_txt(data: bytes) -> tuple[str, str]:
    if not data:
        raise TextDecodeError("文件内容为空")

    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = data.decode(encoding)
            normalized = text.replace("\r\n", "\n").replace("\r", "\n")
            if not normalized.strip():
                raise TextDecodeError("文件中没有可阅读的文字")
            return normalized, encoding
        except UnicodeDecodeError:
            continue

    raise TextDecodeError("无法识别文本编码，请使用 UTF-8 或 GB18030 编码")


def _content_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start] in "\n \t\u3000":
        start += 1
    while end > start and text[end - 1] in "\n \t\u3000":
        end -= 1
    return start, end


def split_chapters(text: str) -> list[ParsedChapter]:
    matches = list(CHAPTER_PATTERN.finditer(text))
    if not matches:
        start, end = _content_bounds(text, 0, len(text))
        return [
            ParsedChapter(
                number=1,
                title="正文",
                content=text[start:end],
                start_offset=start,
                end_offset=end,
            )
        ]

    chapters: list[ParsedChapter] = []

    preface_start, preface_end = _content_bounds(text, 0, matches[0].start())
    if preface_start < preface_end:
        chapters.append(
            ParsedChapter(
                number=1,
                title="卷首",
                content=text[preface_start:preface_end],
                start_offset=preface_start,
                end_offset=preface_end,
            )
        )

    for index, match in enumerate(matches):
        raw_start = match.end()
        raw_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        start, end = _content_bounds(text, raw_start, raw_end)
        chapters.append(
            ParsedChapter(
                number=len(chapters) + 1,
                title=match.group(1).strip(),
                content=text[start:end],
                start_offset=start,
                end_offset=end,
            )
        )

    return chapters

