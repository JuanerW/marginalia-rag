import io
import zipfile

import pytest

from src.services.epub_parser import EpubParseError, parse_epub


def make_epub() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
            <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
              <rootfiles>
                <rootfile full-path="EPUB/package.opf"
                  media-type="application/oebps-package+xml"/>
              </rootfiles>
            </container>""",
        )
        archive.writestr(
            "EPUB/package.opf",
            """<?xml version="1.0"?>
            <package xmlns="http://www.idpf.org/2007/opf" version="3.0">
              <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
                <dc:title>测试 EPUB</dc:title>
                <dc:creator>测试作者</dc:creator>
              </metadata>
              <manifest>
                <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"
                  properties="nav"/>
                <item id="c1" href="text/chapter1.xhtml"
                  media-type="application/xhtml+xml"/>
                <item id="c2" href="text/chapter2.xhtml"
                  media-type="application/xhtml+xml"/>
              </manifest>
              <spine>
                <itemref idref="c1"/>
                <itemref idref="c2"/>
              </spine>
            </package>""",
        )
        archive.writestr(
            "EPUB/nav.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml"><body>
              <nav><ol>
                <li><a href="text/chapter1.xhtml#start">第一章 开始</a></li>
                <li><a href="text/chapter2.xhtml">第二章 相遇</a></li>
              </ol></nav>
            </body></html>""",
        )
        archive.writestr(
            "EPUB/text/chapter1.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml"><body>
              <h1 id="start">错误的文内标题</h1><p>第一段。</p><p>第二段。</p>
              <script>不应出现</script>
            </body></html>""",
        )
        archive.writestr(
            "EPUB/text/chapter2.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml"><body>
              <h1>第二章</h1><p>故事继续。</p>
            </body></html>""",
        )
    return output.getvalue()


def test_parse_epub3_metadata_spine_and_toc() -> None:
    book = parse_epub(make_epub())

    assert book.title == "测试 EPUB"
    assert book.author == "测试作者"
    assert [chapter.title for chapter in book.chapters] == ["第一章 开始", "第二章 相遇"]
    assert [chapter.spine_index for chapter in book.chapters] == [0, 1]
    assert book.chapters[0].source_href == "EPUB/text/chapter1.xhtml"
    assert book.chapters[0].fragment_id == "start"
    assert "第一段。" in book.chapters[0].content
    assert "不应出现" not in book.chapters[0].content
    assert book.chapters[1].start_offset > book.chapters[0].end_offset


def test_reject_non_epub() -> None:
    with pytest.raises(EpubParseError):
        parse_epub(b"not a zip")

