from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE = PROJECT_ROOT / "benchmark" / "pipeline.py"

PROFILES = (
    ("paragraph-small", "paragraph", 350, 500, 50),
    ("paragraph-medium", "paragraph", 700, 900, 100),
    ("paragraph-large", "paragraph", 1100, 1400, 150),
    ("fixed-small", "fixed", 400, 400, 50),
    ("fixed-medium", "fixed", 800, 800, 100),
    ("fixed-large", "fixed", 1200, 1200, 150),
)


def run_profile(
    epub: Path,
    ollama_url: str,
    model: str,
    profile: tuple[str, str, int, int, int],
) -> dict[str, Any]:
    name, strategy, target, maximum, overlap = profile
    result_dir = PROJECT_ROOT / "benchmark" / "results" / "matrix" / name
    command = [
        sys.executable,
        str(PIPELINE),
        "--epub",
        str(epub),
        "--ollama-url",
        ollama_url,
        "--model",
        model,
        "--strategy",
        strategy,
        "--target-size",
        str(target),
        "--max-size",
        str(maximum),
        "--overlap",
        str(overlap),
        "--result-dir",
        str(result_dir),
    ]
    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    summary = json.loads(
        (result_dir / "summary.json").read_text(encoding="utf-8")
    )
    summary["profile_name"] = name
    return summary


def markdown_report(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Chunk 策略对比",
        "",
        "主指标是开放相关集合上的 Hit@10、Recall@10 和 nDCG@10。",
        (
            "人物、物件、组织和角色题将同章内包含实体词的所有 Chunk 视为相关；"
            "事件与关系题继续使用人工证据区间。"
        ),
        "",
        (
        "| Profile | Chunks | Mean chars | Method | Hit@5 | Hit@10 | "
        "Recall@10 | Precision@10 | nDCG@10 | MRR |"
        ),
        "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        for method in ("bm25", "dense", "hybrid"):
            metrics = result["metrics"][method]
            lines.append(
                f"| {result['profile_name']} | {result['chunk_count']} | "
                f"{result['chunk_length']['mean']:.1f} | {method} | "
                f"{metrics['hit_at_5']:.3f} | {metrics['hit_at_10']:.3f} | "
                f"{metrics['recall_at_10']:.3f} | "
                f"{metrics['precision_at_10']:.3f} | "
                f"{metrics['ndcg_at_10']:.3f} | {metrics['mrr']:.3f} |"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epub", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="bge-m3:latest")
    args = parser.parse_args()

    results = [
        run_profile(args.epub, args.ollama_url, args.model, profile)
        for profile in PROFILES
    ]
    report_dir = PROJECT_ROOT / "benchmark" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "chunk_comparison.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown = markdown_report(results)
    (report_dir / "chunk_comparison.md").write_text(
        markdown,
        encoding="utf-8",
    )
    print(markdown)


if __name__ == "__main__":
    main()
