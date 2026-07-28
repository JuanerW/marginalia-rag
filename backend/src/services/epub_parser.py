import html
import io
import posixpath
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote
from xml.etree import ElementTree

MAX_EPUB_SIZE = 50 * 1024 * 1024
MAX_EPUB_UNCOMPRESSED_SIZE = 200 * 1024 * 1024
MAX_EPUB_ENTRIES = 5000
BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "div",
    "figcaption",
    "figure",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tr",
    "ul",
}
SKIP_TAGS = {"script", "style", "svg"}


class EpubParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedEpubChapter:
    number: int
    spine_index: int
    title: str
    content: str
    source_href: str
    fragment_id: str | None
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class ParsedEpub:
    title: str | None
    author: str | None
    chapters: list[ParsedEpubChapter]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _safe_member_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise EpubParseError("EPUB 包含不安全的文件路径")
    return posixpath.normpath(normalized)


def _read_xml(archive: zipfile.ZipFile, name: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(archive.read(name))
    except KeyError as exc:
        raise EpubParseError(f"EPUB 缺少必要文件：{name}") from exc
    except ElementTree.ParseError as exc:
        raise EpubParseError(f"EPUB XML 无法解析：{name}") from exc


def _resolve(base_file: str, href: str) -> tuple[str, str | None]:
    decoded = unquote(href)
    file_part, _, fragment = decoded.partition("#")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(base_file), file_part))
    return _safe_member_name(resolved), fragment or None


def _normalized_text(parts: list[str]) -> str:
    text = html.unescape("".join(parts)).replace("\u00a0", " ").replace("\u3000", "  ")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    paragraphs: list[str] = []
    for line in lines:
        if line:
            paragraphs.append(line)
    return "\n\n".join(paragraphs).strip()


def _xml_text(root: ElementTree.Element) -> str:
    parts: list[str] = []

    def walk(element: ElementTree.Element) -> None:
        tag = _local_name(element.tag)
        if tag in SKIP_TAGS:
            return
        if tag in BLOCK_TAGS and parts and not parts[-1].endswith("\n"):
            parts.append("\n")
        if element.text:
            parts.append(element.text)
        for child in element:
            if _local_name(child.tag) == "br":
                parts.append("\n")
            else:
                walk(child)
            if child.tail:
                parts.append(child.tail)
        if tag in BLOCK_TAGS:
            parts.append("\n")

    body = next((node for node in root.iter() if _local_name(node.tag) == "body"), root)
    walk(body)
    return _normalized_text(parts)


class _FallbackTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        elif not self.skip_depth and (tag in BLOCK_TAGS or tag == "br"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def _document_text(data: bytes) -> str:
    try:
        return _xml_text(ElementTree.fromstring(data))
    except ElementTree.ParseError:
        parser = _FallbackTextParser()
        parser.feed(data.decode("utf-8", errors="replace"))
        return _normalized_text(parser.parts)


def _document_title(data: bytes) -> str | None:
    try:
        root = ElementTree.fromstring(data)
        for node in root.iter():
            if _local_name(node.tag) in {"h1", "h2", "title"}:
                value = " ".join("".join(node.itertext()).split())
                if value:
                    return value[:255]
    except ElementTree.ParseError:
        return None
    return None


def _epub3_toc(
    archive: zipfile.ZipFile,
    opf_path: str,
    manifest: dict[str, dict[str, str]],
) -> dict[str, tuple[str, str | None]]:
    nav_item = next(
        (item for item in manifest.values() if "nav" in item.get("properties", "").split()),
        None,
    )
    if not nav_item:
        return {}
    nav_path, _ = _resolve(opf_path, nav_item["href"])
    root = _read_xml(archive, nav_path)
    titles: dict[str, tuple[str, str | None]] = {}
    for anchor in (node for node in root.iter() if _local_name(node.tag) == "a"):
        href = anchor.attrib.get("href")
        title = " ".join("".join(anchor.itertext()).split())
        if href and title:
            resolved, fragment = _resolve(nav_path, href)
            titles.setdefault(resolved, (title[:255], fragment))
    return titles


def _epub2_toc(
    archive: zipfile.ZipFile,
    opf_path: str,
    opf_root: ElementTree.Element,
    manifest: dict[str, dict[str, str]],
) -> dict[str, tuple[str, str | None]]:
    spine = next((node for node in opf_root.iter() if _local_name(node.tag) == "spine"), None)
    toc_id = spine.attrib.get("toc") if spine is not None else None
    if not toc_id or toc_id not in manifest:
        return {}
    ncx_path, _ = _resolve(opf_path, manifest[toc_id]["href"])
    root = _read_xml(archive, ncx_path)
    titles: dict[str, tuple[str, str | None]] = {}
    for point in (node for node in root.iter() if _local_name(node.tag) == "navpoint"):
        label = next(
            (
                " ".join("".join(node.itertext()).split())
                for node in point.iter()
                if _local_name(node.tag) == "navlabel"
            ),
            "",
        )
        content = next(
            (node for node in point.iter() if _local_name(node.tag) == "content"),
            None,
        )
        if label and content is not None and content.attrib.get("src"):
            resolved, fragment = _resolve(ncx_path, content.attrib["src"])
            titles.setdefault(resolved, (label[:255], fragment))
    return titles


def parse_epub(data: bytes) -> ParsedEpub:
    if not data or not zipfile.is_zipfile(io.BytesIO(data)):
        raise EpubParseError("文件不是有效的 EPUB")

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_EPUB_ENTRIES:
            raise EpubParseError("EPUB 内部文件数量过多")
        total_size = 0
        safe_names: set[str] = set()
        for entry in entries:
            safe_names.add(_safe_member_name(entry.filename))
            total_size += entry.file_size
            if total_size > MAX_EPUB_UNCOMPRESSED_SIZE:
                raise EpubParseError("EPUB 解压后内容超过 200 MB")
            if entry.flag_bits & 0x1:
                raise EpubParseError("暂不支持加密 EPUB")

        container = _read_xml(archive, "META-INF/container.xml")
        rootfile = next(
            (node for node in container.iter() if _local_name(node.tag) == "rootfile"),
            None,
        )
        if rootfile is None or not rootfile.attrib.get("full-path"):
            raise EpubParseError("EPUB 没有声明 OPF 文件")
        opf_path = _safe_member_name(rootfile.attrib["full-path"])
        if opf_path not in safe_names:
            raise EpubParseError("EPUB 声明的 OPF 文件不存在")
        opf_root = _read_xml(archive, opf_path)

        metadata = next(
            (node for node in opf_root.iter() if _local_name(node.tag) == "metadata"),
            None,
        )
        title = None
        author = None
        if metadata is not None:
            for node in metadata:
                value = " ".join("".join(node.itertext()).split())
                if _local_name(node.tag) == "title" and value and title is None:
                    title = value[:255]
                if _local_name(node.tag) == "creator" and value and author is None:
                    author = value[:255]

        manifest: dict[str, dict[str, str]] = {}
        for node in opf_root.iter():
            if _local_name(node.tag) == "item" and node.attrib.get("id") and node.attrib.get("href"):
                manifest[node.attrib["id"]] = dict(node.attrib)

        spine_refs = [
            node.attrib["idref"]
            for node in opf_root.iter()
            if _local_name(node.tag) == "itemref"
            and node.attrib.get("idref")
            and node.attrib.get("linear", "yes") != "no"
        ]
        toc = _epub3_toc(archive, opf_path, manifest)
        if not toc:
            toc = _epub2_toc(archive, opf_path, opf_root, manifest)

        chapters: list[ParsedEpubChapter] = []
        cursor = 0
        for spine_index, item_id in enumerate(spine_refs):
            item = manifest.get(item_id)
            if not item:
                continue
            media_type = item.get("media-type", "")
            if media_type not in {"application/xhtml+xml", "text/html"}:
                continue
            source_href, _ = _resolve(opf_path, item["href"])
            try:
                document = archive.read(source_href)
            except KeyError:
                continue
            content = _document_text(document)
            if not content:
                continue
            toc_title, fragment = toc.get(source_href, (None, None))
            chapter_title = toc_title or _document_title(document) or f"第 {len(chapters) + 1} 章"
            start = cursor
            end = start + len(content)
            chapters.append(
                ParsedEpubChapter(
                    number=len(chapters) + 1,
                    spine_index=spine_index,
                    title=chapter_title[:255],
                    content=content,
                    source_href=source_href,
                    fragment_id=fragment,
                    start_offset=start,
                    end_offset=end,
                )
            )
            cursor = end + 2

    if not chapters:
        raise EpubParseError("EPUB 中没有可阅读的正文")
    return ParsedEpub(title=title, author=author, chapters=chapters)
