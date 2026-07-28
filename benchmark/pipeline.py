from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from src.services.epub_parser import ParsedEpubChapter, parse_epub

BODY_SEPARATOR = "--------------------"
SENTENCE_PATTERN = re.compile(
    r".*?[。！？!?；;](?:[”’」』])?|.+$",
    re.DOTALL,
)
CHINESE_PATTERN = re.compile(r"[\u3400-\u9fff]")
ALNUM_PATTERN = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class Segment:
    start: int
    end: int


@dataclass(frozen=True)
class Chunk:
    id: str
    chapter_number: int
    chapter_title: str
    source_href: str
    start_offset: int
    end_offset: int
    content: str


def load_questions(path: Path) -> list[dict[str, Any]]:
    questions = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(questions) != 30:
        raise ValueError(f"Benchmark 应包含 30 道题，实际为 {len(questions)}")
    for question in questions:
        if question["query_type"] in {
            "person",
            "object",
            "organization",
            "role",
        }:
            subject = re.split(
                r"是谁|是什么|在第",
                question["question"],
                maxsplit=1,
            )[0]
            question.setdefault("relevant_terms", [subject])
    return questions


def select_first_three_chapters(epub_path: Path) -> list[ParsedEpubChapter]:
    book = parse_epub(epub_path.read_bytes())
    selected: list[ParsedEpubChapter] = []
    for expected in ("第一回", "第二回", "第三回"):
        chapter = next((item for item in book.chapters if item.title.startswith(expected)), None)
        if chapter is None:
            raise ValueError(f"EPUB 中没有找到 {expected}")
        selected.append(chapter)
    return selected


def body_end(content: str) -> int:
    position = content.find(BODY_SEPARATOR)
    return position if position >= 0 else len(content)


def validate_questions(
    questions: list[dict[str, Any]],
    chapters: list[ParsedEpubChapter],
) -> None:
    chapter_map = {index + 1: chapter for index, chapter in enumerate(chapters)}
    ids: set[str] = set()
    counts = Counter()
    for question in questions:
        question_id = question["id"]
        if question_id in ids:
            raise ValueError(f"重复问题 ID：{question_id}")
        ids.add(question_id)
        chapter_number = question["chapter_number"]
        counts[chapter_number] += 1
        chapter = chapter_map[chapter_number]
        limit = body_end(chapter.content)
        for evidence in question["evidence"]:
            start = evidence["start_offset"]
            end = evidence["end_offset"]
            if not (0 <= start < end <= limit):
                raise ValueError(
                    f"{question_id} 证据越界：{start}:{end}，正文长度 {limit}"
                )
            if not chapter.content[start:end].strip():
                raise ValueError(f"{question_id} 证据为空")
    if counts != Counter({1: 10, 2: 10, 3: 10}):
        raise ValueError(f"每回应有 10 道题，实际为 {dict(counts)}")


def paragraph_segments(content: str, max_size: int) -> list[Segment]:
    limit = body_end(content)
    body = content[:limit]
    segments: list[Segment] = []
    for match in re.finditer(r"\S(?:.*?\S)?(?=\n{2,}|\Z)", body, re.DOTALL):
        start, end = match.span()
        if end - start <= max_size:
            segments.append(Segment(start, end))
            continue
        paragraph = content[start:end]
        cursor = 0
        for sentence in SENTENCE_PATTERN.finditer(paragraph):
            sentence_start = start + sentence.start()
            sentence_end = start + sentence.end()
            while sentence_end - sentence_start > max_size:
                segments.append(Segment(sentence_start, sentence_start + max_size))
                sentence_start += max_size
            if sentence_start < sentence_end:
                segments.append(Segment(sentence_start, sentence_end))
            cursor = sentence.end()
        if cursor < len(paragraph):
            segments.append(Segment(start + cursor, end))
    return segments


def chunk_chapter(
    chapter: ParsedEpubChapter,
    chapter_number: int,
    target_size: int,
    max_size: int,
    overlap: int,
) -> list[Chunk]:
    segments = paragraph_segments(chapter.content, max_size)
    chunks: list[Chunk] = []
    start_index = 0
    while start_index < len(segments):
        end_index = start_index
        while end_index + 1 < len(segments):
            proposed = segments[end_index + 1].end - segments[start_index].start
            if proposed > max_size:
                break
            end_index += 1
            current_size = segments[end_index].end - segments[start_index].start
            if current_size >= target_size:
                break

        start = segments[start_index].start
        end = segments[end_index].end
        content = chapter.content[start:end]
        chunks.append(
            Chunk(
                id=f"c{chapter_number:02d}_{len(chunks) + 1:03d}",
                chapter_number=chapter_number,
                chapter_title=chapter.title,
                source_href=chapter.source_href,
                start_offset=start,
                end_offset=end,
                content=content,
            )
        )
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


def build_chunk_set(
    chapters: list[ParsedEpubChapter],
    target_size: int,
    max_size: int,
    overlap: int,
    strategy: str = "paragraph",
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for number, chapter in enumerate(chapters, 1):
        if strategy == "paragraph":
            chapter_chunks = chunk_chapter(
                chapter, number, target_size, max_size, overlap
            )
        elif strategy == "fixed":
            chapter_chunks = fixed_chunks(
                chapter, number, target_size, overlap
            )
        else:
            raise ValueError(f"未知 Chunk 策略：{strategy}")
        chunks.extend(chapter_chunks)
    return chunks


def fixed_chunks(
    chapter: ParsedEpubChapter,
    chapter_number: int,
    size: int,
    overlap: int,
) -> list[Chunk]:
    if overlap >= size:
        raise ValueError("固定窗口 overlap 必须小于 size")
    limit = body_end(chapter.content)
    chunks: list[Chunk] = []
    start = 0
    step = size - overlap
    while start < limit:
        end = min(start + size, limit)
        chunks.append(
            Chunk(
                id=f"c{chapter_number:02d}_{len(chunks) + 1:03d}",
                chapter_number=chapter_number,
                chapter_title=chapter.title,
                source_href=chapter.source_href,
                start_offset=start,
                end_offset=end,
                content=chapter.content[start:end],
            )
        )
        if end == limit:
            break
        start += step
    return chunks


def tokenize(text: str) -> list[str]:
    chinese = CHINESE_PATTERN.findall(text)
    tokens = chinese + [a + b for a, b in pairwise(chinese)]
    tokens.extend(token.lower() for token in ALNUM_PATTERN.findall(text))
    return tokens


class BM25:
    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents = [tokenize(document) for document in documents]
        self.lengths = [len(document) for document in self.documents]
        self.avg_length = sum(self.lengths) / max(1, len(self.lengths))
        self.term_frequencies = [Counter(document) for document in self.documents]
        document_frequency = Counter()
        for document in self.documents:
            document_frequency.update(set(document))
        total = len(self.documents)
        self.idf = {
            term: math.log(1 + (total - count + 0.5) / (count + 0.5))
            for term, count in document_frequency.items()
        }

    def scores(self, query: str) -> list[float]:
        query_terms = tokenize(query)
        scores: list[float] = []
        for frequencies, length in zip(
            self.term_frequencies, self.lengths, strict=True
        ):
            score = 0.0
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * length / self.avg_length
                )
                score += self.idf.get(term, 0.0) * (
                    frequency * (self.k1 + 1) / denominator
                )
            scores.append(score)
        return scores


def ollama_embed(
    texts: list[str],
    base_url: str,
    model: str,
    batch_size: int = 16,
) -> list[list[float]]:
    embeddings: list[list[float]] = []
    endpoint = f"{base_url.rstrip('/')}/api/embed"
    for start in range(0, len(texts), batch_size):
        payload = json.dumps(
            {"model": model, "input": texts[start : start + batch_size]}
        ).encode()
        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.load(response)
        embeddings.extend(result["embeddings"])
    return embeddings


def normalized(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def dense_scores(query_vector: list[float], vectors: list[list[float]]) -> list[float]:
    query = normalized(query_vector)
    return [
        sum(left * right for left, right in zip(query, vector, strict=True))
        for vector in vectors
    ]


def rank_indices(scores: list[float], allowed: list[bool]) -> list[int]:
    return sorted(
        (index for index, is_allowed in enumerate(allowed) if is_allowed),
        key=lambda index: scores[index],
        reverse=True,
    )


def reciprocal_rank_fusion(
    first: list[int],
    second: list[int],
    rank_constant: int = 60,
) -> tuple[list[int], dict[int, float]]:
    scores: dict[int, float] = {}
    for ranking in (first, second):
        for rank, index in enumerate(ranking, 1):
            scores[index] = scores.get(index, 0.0) + 1 / (rank_constant + rank)
    return sorted(scores, key=scores.get, reverse=True), scores


def relevance(question: dict[str, Any], chunk: Chunk) -> int:
    if chunk.chapter_number != question["chapter_number"]:
        return 0
    terms = question.get("relevant_terms", [])
    if terms and any(term in chunk.content for term in terms):
        return 2
    best_coverage = 0.0
    for evidence in question["evidence"]:
        start = max(chunk.start_offset, evidence["start_offset"])
        end = min(chunk.end_offset, evidence["end_offset"])
        overlap = max(0, end - start)
        evidence_length = evidence["end_offset"] - evidence["start_offset"]
        best_coverage = max(best_coverage, overlap / evidence_length)
    if best_coverage >= 0.8:
        return 2
    return 1 if best_coverage > 0 else 0


def dcg(grades: list[int]) -> float:
    return sum(
        (2**grade - 1) / math.log2(rank + 1)
        for rank, grade in enumerate(grades, 1)
    )


def evaluate_method(
    method: str,
    questions: list[dict[str, Any]],
    chunks: list[Chunk],
    rankings: dict[str, list[int]],
    score_maps: dict[str, dict[int, float]],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    hit_totals = {1: 0, 3: 0, 5: 0, 10: 0}
    recall_totals: dict[int, list[float]] = {5: [], 10: []}
    precision_totals: dict[int, list[float]] = {5: [], 10: []}
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    violations = 0
    details: list[dict[str, Any]] = []

    for question in questions:
        ranking = rankings[question["id"]]
        grades = [relevance(question, chunks[index]) for index in ranking]
        for k in hit_totals:
            hit_totals[k] += int(any(grade == 2 for grade in grades[:k]))
        relevant_total = sum(
            relevance(question, chunk) == 2 for chunk in chunks
        )
        for k, recall_values in recall_totals.items():
            retrieved = sum(grade == 2 for grade in grades[:k])
            recall_values.append(
                retrieved / relevant_total if relevant_total else 0.0
            )
            precision_totals[k].append(retrieved / min(k, len(grades)))
        first_relevant = next(
            (rank for rank, grade in enumerate(grades, 1) if grade == 2),
            None,
        )
        reciprocal_ranks.append(1 / first_relevant if first_relevant else 0.0)
        ideal = sorted(
            [relevance(question, chunk) for chunk in chunks],
            reverse=True,
        )[:10]
        ideal_score = dcg(ideal)
        ndcgs.append(dcg(grades[:10]) / ideal_score if ideal_score else 0.0)
        top_results = []
        for index in ranking[:5]:
            chunk = chunks[index]
            if chunk.chapter_number > question["max_read_chapter"]:
                violations += 1
            top_results.append(
                {
                    "chunk_id": chunk.id,
                    "chapter_number": chunk.chapter_number,
                    "start_offset": chunk.start_offset,
                    "end_offset": chunk.end_offset,
                    "score": score_maps[question["id"]].get(index, 0.0),
                    "relevance": relevance(question, chunk),
                    "preview": chunk.content[:160].replace("\n", " "),
                }
            )
        details.append(
            {
                "id": question["id"],
                "question": question["question"],
                "method": method,
                "first_relevant_rank": first_relevant,
                "top_results": top_results,
            }
        )

    total = len(questions)
    metrics = {
        "hit_at_1": hit_totals[1] / total,
        "hit_at_3": hit_totals[3] / total,
        "hit_at_5": hit_totals[5] / total,
        "hit_at_10": hit_totals[10] / total,
        "recall_at_5": sum(recall_totals[5]) / total,
        "recall_at_10": sum(recall_totals[10]) / total,
        "precision_at_5": sum(precision_totals[5]) / total,
        "precision_at_10": sum(precision_totals[10]) / total,
        "mrr": sum(reciprocal_ranks) / total,
        "ndcg_at_10": sum(ndcgs) / total,
        "boundary_violation_rate": violations / (total * 5),
    }
    return metrics, details


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epub", type=Path, required=True)
    parser.add_argument(
        "--questions",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "questions.jsonl",
    )
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="bge-m3:latest")
    parser.add_argument("--target-size", type=int, default=700)
    parser.add_argument("--max-size", type=int, default=900)
    parser.add_argument("--overlap", type=int, default=100)
    parser.add_argument(
        "--strategy",
        choices=("paragraph", "fixed"),
        default="paragraph",
    )
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=PROJECT_ROOT / "benchmark" / "results",
    )
    args = parser.parse_args()

    questions = load_questions(args.questions)
    chapters = select_first_three_chapters(args.epub)
    validate_questions(questions, chapters)
    chunks = build_chunk_set(
        chapters,
        target_size=args.target_size,
        max_size=args.max_size,
        overlap=args.overlap,
        strategy=args.strategy,
    )

    profile = (
        f"{args.strategy}_{args.target_size}_{args.max_size}_{args.overlap}"
    )
    cache_key = hashlib.sha256(
        (
            args.model
            + profile
            + "".join(hashlib.sha256(chunk.content.encode()).hexdigest() for chunk in chunks)
        ).encode()
    ).hexdigest()[:16]
    cache_path = PROJECT_ROOT / "benchmark" / "cache" / f"{cache_key}.json"
    if cache_path.exists():
        vectors = json.loads(cache_path.read_text(encoding="utf-8"))["vectors"]
    else:
        vectors = ollama_embed(
            [chunk.content for chunk in chunks],
            args.ollama_url,
            args.model,
        )
        write_json(
            cache_path,
            {"model": args.model, "profile": profile, "vectors": vectors},
        )
    vectors = [normalized(vector) for vector in vectors]

    question_vectors = ollama_embed(
        [question["question"] for question in questions],
        args.ollama_url,
        args.model,
    )
    bm25 = BM25([chunk.content for chunk in chunks])

    method_rankings: dict[str, dict[str, list[int]]] = {
        "bm25": {},
        "dense": {},
        "hybrid": {},
    }
    method_scores: dict[str, dict[str, dict[int, float]]] = {
        "bm25": {},
        "dense": {},
        "hybrid": {},
    }

    for question, query_vector in zip(questions, question_vectors, strict=True):
        allowed = [
            chunk.chapter_number <= question["max_read_chapter"] for chunk in chunks
        ]
        bm25_values = bm25.scores(question["question"])
        dense_values = dense_scores(query_vector, vectors)
        bm25_ranking = rank_indices(bm25_values, allowed)
        dense_ranking = rank_indices(dense_values, allowed)
        hybrid_ranking, hybrid_values = reciprocal_rank_fusion(
            bm25_ranking, dense_ranking
        )
        question_id = question["id"]
        method_rankings["bm25"][question_id] = bm25_ranking
        method_rankings["dense"][question_id] = dense_ranking
        method_rankings["hybrid"][question_id] = hybrid_ranking
        method_scores["bm25"][question_id] = dict(enumerate(bm25_values))
        method_scores["dense"][question_id] = dict(enumerate(dense_values))
        method_scores["hybrid"][question_id] = hybrid_values

    all_metrics: dict[str, dict[str, float]] = {}
    all_details: list[dict[str, Any]] = []
    for method in ("bm25", "dense", "hybrid"):
        metrics, details = evaluate_method(
            method,
            questions,
            chunks,
            method_rankings[method],
            method_scores[method],
        )
        all_metrics[method] = metrics
        all_details.extend(details)

    result_dir = args.result_dir
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "epub": str(args.epub),
        "model": args.model,
        "embedding_dimension": len(vectors[0]),
        "chunk_profile": {
            "strategy": args.strategy,
            "target_size": args.target_size,
            "max_size": args.max_size,
            "overlap": args.overlap,
        },
        "chapter_count": len(chapters),
        "chunk_count": len(chunks),
        "chunk_length": {
            "min": min(len(chunk.content) for chunk in chunks),
            "mean": sum(len(chunk.content) for chunk in chunks) / len(chunks),
            "max": max(len(chunk.content) for chunk in chunks),
        },
        "question_count": len(questions),
        "metrics": all_metrics,
    }
    write_json(result_dir / "summary.json", report)
    write_json(result_dir / "details.json", all_details)
    write_json(result_dir / "chunks.json", [asdict(chunk) for chunk in chunks])
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
