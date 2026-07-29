# 三国演义前三回检索 Benchmark

这套基准用于比较同一 Chunk Set 上的三种检索方法：

- BM25：中文字符 unigram/bigram；
- Dense：Ollama `bge-m3:latest`；
- Hybrid：BM25 与 Dense 的 Reciprocal Rank Fusion。

## 数据

`questions.jsonl` 共 30 道简单题，每回 10 道。题目以人物、物件、组织和显著事件为主。证据偏移相对于 EPUB 对应 XHTML 清洗后的章节正文，先标注证据，再生成 Chunk，避免偏向某一种切块方案。

每条数据包含：

```json
{
  "id": "sgyy_c1_q01",
  "question": "东汉末年的混乱主要从哪两位皇帝时期开始？",
  "chapter_number": 1,
  "evidence": [{"start_offset": 113, "end_offset": 307}],
  "query_type": "fact",
  "difficulty": "easy",
  "max_read_chapter": 1
}
```

## 第一轮配置

- 范围：《三国演义》第一至第三回；
- Chunk：段落优先，目标 700 字，最大 900 字，重叠约 100 字；
- Embedding：Ollama `bge-m3:latest`，1024 维；
- Top-K：1、3、5、10；
- 指标：Hit@K、Recall@5/10、MRR、nDCG@10、越界率；
- 无剧透过滤：检索候选在排序前按 `max_read_chapter` 过滤。

## 相关性定义

- 人物、物件、组织、角色：同章内任何包含目标实体词的 Chunk 都是强相关；
- 事件、关系：覆盖人工标注证据 80% 以上为强相关，部分覆盖为弱相关；
- 因此“张角是谁？”不再只有一个标准答案，而是拥有多个相关 Chunk。

## Chunk 策略矩阵

运行六组段落优先/固定窗口配置：

```powershell
python benchmark/compare_chunks.py `
  --epub "C:\Users\JuanerW\Downloads\SanGuoYanYi（JiaoZhuBen）.epub"
```

可提交的汇总报告写入 `benchmark/reports/`；逐题结果和 Embedding 缓存仍不提交。

## 运行

在项目根目录执行：

```powershell
conda activate reader
python benchmark/pipeline.py `
  --epub "C:\Users\JuanerW\Downloads\SanGuoYanYi（JiaoZhuBen）.epub" `
  --ollama-url http://127.0.0.1:11434 `
  --model bge-m3:latest
```

输出写入 `benchmark/results/`，Embedding 缓存写入 `benchmark/cache/`。这些生成文件默认不提交 Git。
