from collections.abc import Callable

from core.domain.knowledge import ExtractedContent, SourceFile
from knowledge.chunker import TokenChunker


def test_long_text_produces_multiple_overlapping_chunks(
    make_source_file: Callable[..., SourceFile],
) -> None:
    text = "".join(str(i % 10) for i in range(5_000))
    content = ExtractedContent(
        source=make_source_file(path="/docs/long.md", media_type="text/markdown"),
        text=text,
        metadata={},
    )

    chunks = TokenChunker(chunk_size_tokens=512, chunk_overlap_tokens=51).chunk(content)

    assert len(chunks) > 1
    assert [chunk.position for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].text[-204:] == chunks[1].text[:204]


def test_empty_or_whitespace_text_returns_no_chunks(
    make_source_file: Callable[..., SourceFile],
) -> None:
    chunker = TokenChunker(chunk_size_tokens=512, chunk_overlap_tokens=51)

    assert chunker.chunk(
        ExtractedContent(source=make_source_file(), text="", metadata={})
    ) == ()
    assert chunker.chunk(
        ExtractedContent(source=make_source_file(), text="  \n\t  ", metadata={})
    ) == ()


def test_short_text_produces_single_deterministic_chunk(
    make_source_file: Callable[..., SourceFile],
) -> None:
    content = ExtractedContent(
        source=make_source_file(path="/docs/short.txt"),
        text="short text",
        metadata={},
    )
    chunker = TokenChunker(chunk_size_tokens=512, chunk_overlap_tokens=51)

    first = chunker.chunk(content)
    second = chunker.chunk(content)

    assert len(first) == 1
    assert first == second
    assert first[0].chunk_id == "/docs/short.txt#0"
    assert first[0].position == 0
    assert first[0].text == "short text"


def test_tabular_content_chunks_by_row_groups_without_overlap(
    make_source_file: Callable[..., SourceFile],
) -> None:
    rows = [f"row-{idx},value-{idx}" for idx in range(25)]
    content = ExtractedContent(
        source=make_source_file(path="/docs/data.csv", media_type="text/csv"),
        text="\n".join(rows),
        metadata={},
    )

    chunks = TokenChunker(chunk_size_tokens=512, chunk_overlap_tokens=51).chunk(content)

    assert len(chunks) == 3
    assert [chunk.position for chunk in chunks] == [0, 1, 2]
    assert chunks[0].text == "\n".join(rows[:10])
    assert chunks[1].text == "\n".join(rows[10:20])
    assert chunks[2].text == "\n".join(rows[20:])
