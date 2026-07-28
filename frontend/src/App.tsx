import {
  FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

type Novel = {
  id: string;
  title: string;
  author: string | null;
  source_filename: string;
  source_format: "epub" | "txt";
  status: string;
  chapter_count: number;
  created_at: string;
};

type ChapterSummary = {
  id: string;
  number: number;
  title: string;
  start_offset: number;
  end_offset: number;
};

type Chapter = ChapterSummary & { content: string };

type Progress = {
  display_chapter_number: number;
  display_offset: number;
  furthest_chapter_number: number;
  furthest_offset: number;
  reader_key: string;
};

type ReaderSettings = {
  theme: "paper" | "sepia" | "dark";
  fontSize: number;
  lineHeight: number;
};

const defaultSettings: ReaderSettings = {
  theme: "paper",
  fontSize: 19,
  lineHeight: 1.9,
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

async function apiError(response: Response) {
  try {
    const payload = await response.json();
    return payload.detail ?? "请求失败，请稍后重试";
  } catch {
    return "请求失败，请稍后重试";
  }
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(await apiError(response));
  return response.json();
}

export default function App() {
  const [novels, setNovels] = useState<Novel[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");
  const [activeNovel, setActiveNovel] = useState<Novel | null>(null);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [readerLoading, setReaderLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState<ReaderSettings>(() => {
    try {
      const saved = window.localStorage.getItem("reader-settings");
      return saved ? { ...defaultSettings, ...JSON.parse(saved) } : defaultSettings;
    } catch {
      return defaultSettings;
    }
  });
  const fileInput = useRef<HTMLInputElement>(null);
  const readerViewport = useRef<HTMLDivElement>(null);
  const saveTimer = useRef<number | null>(null);

  const loadNovels = useCallback(async () => {
    setLoading(true);
    try {
      setNovels(await getJson<Novel[]>(`${API_URL}/novels`));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法加载书架");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadNovels();
  }, [loadNovels]);

  useEffect(() => {
    window.localStorage.setItem("reader-settings", JSON.stringify(settings));
  }, [settings]);

  async function saveProgress(chapterNumber: number, offset: number) {
    if (!activeNovel) return;
    const response = await fetch(`${API_URL}/novels/${activeNovel.id}/progress`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        display_chapter_number: chapterNumber,
        display_offset: offset,
        reader_key: "local",
      }),
    });
    if (response.ok) setProgress(await response.json());
  }

  async function loadChapter(
    novel: Novel,
    chapterNumber: number,
    restoreOffset = 0,
  ) {
    setReaderLoading(true);
    try {
      const loaded = await getJson<Chapter>(
        `${API_URL}/novels/${novel.id}/chapters/${chapterNumber}`,
      );
      setChapter(loaded);
      requestAnimationFrame(() => {
        const viewport = readerViewport.current;
        if (!viewport) return;
        const maxScroll = viewport.scrollHeight - viewport.clientHeight;
        viewport.scrollTop =
          loaded.content.length > 0
            ? maxScroll * (restoreOffset / loaded.content.length)
            : 0;
      });
    } finally {
      setReaderLoading(false);
    }
  }

  async function openNovel(novel: Novel) {
    setActiveNovel(novel);
    setReaderLoading(true);
    setMessage("");
    try {
      const [loadedChapters, loadedProgress] = await Promise.all([
        getJson<ChapterSummary[]>(`${API_URL}/novels/${novel.id}/chapters`),
        getJson<Progress>(`${API_URL}/novels/${novel.id}/progress`),
      ]);
      setChapters(loadedChapters);
      setProgress(loadedProgress);
      const available = loadedChapters.some(
        (item) => item.number === loadedProgress.display_chapter_number,
      );
      const chapterNumber = available
        ? loadedProgress.display_chapter_number
        : loadedChapters[0]?.number;
      if (chapterNumber) {
        await loadChapter(
          novel,
          chapterNumber,
          available ? loadedProgress.display_offset : 0,
        );
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法打开小说");
      setActiveNovel(null);
    } finally {
      setReaderLoading(false);
    }
  }

  function handleReaderScroll() {
    if (!chapter || !readerViewport.current) return;
    const viewport = readerViewport.current;
    const maxScroll = viewport.scrollHeight - viewport.clientHeight;
    const ratio = maxScroll > 0 ? viewport.scrollTop / maxScroll : 1;
    const offset = Math.min(
      chapter.content.length,
      Math.max(0, Math.round(chapter.content.length * ratio)),
    );
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      void saveProgress(chapter.number, offset);
    }, 500);
  }

  async function goToChapter(number: number, offset = 0) {
    if (!activeNovel || number === chapter?.number) return;
    await saveProgress(number, offset);
    await loadChapter(activeNovel, number, offset);
  }

  function chooseFile(selected: File | null) {
    setFile(selected);
    setMessage("");
    if (selected && !title && selected.name.toLowerCase().endsWith(".txt")) {
      setTitle(selected.name.replace(/\.txt$/i, ""));
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setMessage("请先选择一本 EPUB 或 TXT 小说");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    if (title.trim()) form.append("title", title.trim());
    if (author.trim()) form.append("author", author.trim());
    setUploading(true);
    setMessage("");
    try {
      const response = await fetch(`${API_URL}/novels`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) throw new Error(await apiError(response));
      const uploaded: Novel = await response.json();
      setMessage(`《${uploaded.title}》已解析，共 ${uploaded.chapter_count} 章`);
      setFile(null);
      setTitle("");
      setAuthor("");
      if (fileInput.current) fileInput.current.value = "";
      await loadNovels();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  if (activeNovel) {
    const currentIndex = chapters.findIndex(
      (item) => item.number === chapter?.number,
    );
    const readPercent =
      chapter && progress?.furthest_chapter_number === chapter.number
        ? Math.round(
            (progress.furthest_offset / Math.max(1, chapter.content.length)) * 100,
          )
        : progress && chapter && progress.furthest_chapter_number > chapter.number
          ? 100
          : 0;

    return (
      <div className={`reader-shell theme-${settings.theme}`}>
        <header className="reader-header">
          <button className="text-button" onClick={() => setSidebarOpen(!sidebarOpen)}>
            ☰ 目录
          </button>
          <div className="reader-book-title">
            <strong>{activeNovel.title}</strong>
            <span>{activeNovel.source_format.toUpperCase()} · {chapter?.title ?? "正在载入…"}</span>
          </div>
          <div className="reader-actions">
            <button className="text-button" onClick={() => setSettingsOpen(!settingsOpen)}>
              Aa 设置
            </button>
            <button className="text-button" onClick={() => setActiveNovel(null)}>
              返回书架
            </button>
          </div>
        </header>

        <div className="reader-body">
          <aside className={sidebarOpen ? "chapter-sidebar open" : "chapter-sidebar"}>
            <p className="sidebar-label">CONTENTS</p>
            <h2>章节目录</h2>
            <div className="chapter-list">
              {chapters.map((item) => (
                <button
                  key={item.id}
                  className={item.number === chapter?.number ? "active" : ""}
                  onClick={() => void goToChapter(item.number)}
                >
                  <span>{String(item.number).padStart(2, "0")}</span>
                  {item.title}
                </button>
              ))}
            </div>
          </aside>

          <section className="reading-stage">
            {settingsOpen && (
              <div className="settings-panel">
                <label>
                  主题
                  <span className="theme-options">
                    {(["paper", "sepia", "dark"] as const).map((theme) => (
                      <button
                        key={theme}
                        className={settings.theme === theme ? "selected" : ""}
                        onClick={() => setSettings({ ...settings, theme })}
                      >
                        {theme === "paper" ? "纸白" : theme === "sepia" ? "护眼" : "夜间"}
                      </button>
                    ))}
                  </span>
                </label>
                <label>
                  字号 <strong>{settings.fontSize}px</strong>
                  <input
                    type="range"
                    min="15"
                    max="28"
                    value={settings.fontSize}
                    onChange={(event) =>
                      setSettings({ ...settings, fontSize: Number(event.target.value) })
                    }
                  />
                </label>
                <label>
                  行高 <strong>{settings.lineHeight.toFixed(1)}</strong>
                  <input
                    type="range"
                    min="1.5"
                    max="2.5"
                    step="0.1"
                    value={settings.lineHeight}
                    onChange={(event) =>
                      setSettings({ ...settings, lineHeight: Number(event.target.value) })
                    }
                  />
                </label>
              </div>
            )}

            <div
              ref={readerViewport}
              className="reader-viewport"
              onScroll={handleReaderScroll}
            >
              {readerLoading || !chapter ? (
                <div className="reader-loading">正在翻开这一章…</div>
              ) : (
                <article
                  className="chapter-content"
                  style={{
                    fontSize: `${settings.fontSize}px`,
                    lineHeight: settings.lineHeight,
                  }}
                >
                  <p className="chapter-index">CHAPTER {chapter.number}</p>
                  <h1>{chapter.title}</h1>
                  <div className="chapter-text">
                    {chapter.content.split(/\n{2,}/).map((paragraph, index) => (
                      <p key={`${chapter.id}-${index}`}>{paragraph}</p>
                    ))}
                  </div>
                </article>
              )}
            </div>

            <footer className="reader-footer">
              <button
                disabled={currentIndex <= 0}
                onClick={() => void goToChapter(chapters[currentIndex - 1].number)}
              >
                ← 上一章
              </button>
              <span>本章已读 {Math.min(100, readPercent)}%</span>
              <button
                disabled={currentIndex < 0 || currentIndex >= chapters.length - 1}
                onClick={() => void goToChapter(chapters[currentIndex + 1].number)}
              >
                下一章 →
              </button>
            </footer>
          </section>
        </div>
      </div>
    );
  }

  return (
    <main>
      <nav>
        <span className="brand">未完待续</span>
        <span className="badge">M2 · 电子书阅读器</span>
      </nav>
      <section className="hero">
        <div>
          <p className="eyebrow">SPOILER-FREE AI READER</p>
          <h1>故事向前，<br />剧透止步。</h1>
          <p className="intro">
            EPUB 优先读取内置目录与元数据；TXT 作为兼容格式继续支持。
          </p>
        </div>
        <form className="upload-card" onSubmit={submit}>
          <div className="card-heading">
            <span>添加一本书</span><span className="step">01 / IMPORT</span>
          </div>
          <label className={`dropzone ${file ? "has-file" : ""}`}>
            <input
              ref={fileInput}
              type="file"
              accept=".epub,application/epub+zip,.txt,text/plain"
              onChange={(event) => chooseFile(event.target.files?.[0] ?? null)}
            />
            <span className="file-mark">
              {file ? file.name.split(".").pop()?.toUpperCase() : "+"}
            </span>
            <span>
              <strong>{file?.name ?? "选择 EPUB 或 TXT"}</strong>
              <small>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "EPUB 最大 50 MB"}</small>
            </span>
          </label>
          <div className="fields">
            <label><span>书名</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="优先读取 EPUB 元数据" /></label>
            <label><span>作者</span><input value={author} onChange={(event) => setAuthor(event.target.value)} placeholder="优先读取 EPUB 元数据" /></label>
          </div>
          <button type="submit" disabled={uploading}>
            {uploading ? "正在解析…" : "上传并解析"}
          </button>
          {message && <p className="message" role="status">{message}</p>}
        </form>
      </section>
      <section className="shelf">
        <div className="section-heading">
          <div><p className="eyebrow">YOUR LIBRARY</p><h2>我的书架</h2></div>
          <span>{novels.length} 本小说</span>
        </div>
        {loading ? (
          <div className="empty">正在整理书架…</div>
        ) : novels.length === 0 ? (
          <div className="empty"><span>书架还是空的</span><p>从上方上传一本 EPUB 或 TXT 小说开始。</p></div>
        ) : (
          <div className="book-grid">
            {novels.map((novel, index) => (
              <article className="book" key={novel.id} onClick={() => void openNovel(novel)}>
                <div className={`cover tone-${index % 4}`}>
                  <span className="cover-title">{novel.title}</span>
                  <span className="cover-author">{novel.author || "佚名"}</span>
                </div>
                <div className="book-info">
                  <span className="ready">
                    ● {novel.source_format.toUpperCase()} · 点击继续阅读
                  </span>
                  <h3>{novel.title}</h3>
                  <p>{novel.chapter_count} 章 · {formatDate(novel.created_at)}</p>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
