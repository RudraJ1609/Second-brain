# SecondSelf — System Architecture

> A self-organizing second brain: capture → classify → link → visualize → ask → deploy.

---

## 1. Vision & Design Principles

| Principle | Meaning |
|-----------|---------|
| **File-first** | Notes live as plain Markdown on disk. No database required for v1. |
| **Pipeline, not platform** | Each stage is a CLI/script; later stages consume earlier outputs. |
| **Real data only** | Design for your own notes, not fixtures. |
| **Free / local where possible** | Groq (LLM), sentence-transformers (embeddings), Streamlit Cloud / HF Spaces (hosting). |
| **One product surface** | Week 4 ships a single Streamlit app with graph + ask. |

---

## 2. High-Level System Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│   Capture   │────▶│   Classify   │────▶│  Auto-Link  │────▶│ Build Graph  │
│ capture.py  │     │ classify.py  │     │   link.py   │     │build_graph.py│
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘
       │                    │                    │                    │
       ▼                    ▼                    ▼                    ▼
    raw/*.md            wiki/*.md           wiki/*.md            graph.json
                         + frontmatter      + [[wikilinks]]      + embeddings
                                                                    cache
                                                                         │
                    ┌────────────────────────────────────────────────────┘
                    ▼
           ┌────────────────┐          ┌─────────────────┐
           │   Ask (RAG)    │◀────────▶│  Streamlit App  │
           │    ask.py      │          │     app.py      │
           └────────────────┘          └────────┬────────┘
                    │                           │
                    ▼                           ▼
              Groq LLM                  Public URL
         + local embeddings         (Streamlit Cloud /
                                      HF Spaces)
```

**End-to-end flow**

1. User captures a note / link / file → `raw/`
2. LLM classifies into PARA + tags + summary → `wiki/`
3. Embeddings find related notes → auto-insert `[[links]]`
4. Graph builder exports nodes/edges → `graph.json`
5. User asks a question → retrieve top-k notes → LLM synthesizes answer
6. Streamlit serves graph + search at a public URL

---

## 3. Layered Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Presentation Layer                                      │
│  app.py (Streamlit) · Graph (vis-network/Cytoscape)      │
│  Ask search bar · Hover tooltips · Drag/zoom             │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│  Application / Pipeline Layer                            │
│  capture · classify · link · build_graph · ask           │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│  Intelligence Layer                                      │
│  Groq / Llama 3 (classify + answer)                      │
│  sentence-transformers (embeddings + similarity)         │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│  Data Layer (filesystem)                                 │
│  raw/ · wiki/ · graph.json · embeddings store · .env     │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Component Design

### 4.1 `capture.py` — The Archivist (Week 1)

**Responsibility:** One command that accepts text, URL, or file path and writes a durable raw capture.

**Inputs**
- CLI args / stdin: note text, URL, or local file path

**Processing**
1. Detect type: `note` | `link` | `file`
2. Generate `id` (UUID or ULID) + ISO timestamp
3. For links: optionally fetch title / URL metadata (keep body as URL + note)
4. For files: copy or extract text (PDF/txt/md); store original path in metadata
5. Write Markdown file to `raw/`

**Output schema (`raw/{id}.md`)**

```markdown
---
id: "a1b2c3d4"
type: note | link | file
created_at: "2026-07-17T05:40:00+05:30"
source: null | "https://..." | "C:/path/to/file.pdf"
status: raw
---

<body content here>
```

**CLI example**

```bash
python capture.py "Idea: build a RAG over my notes"
python capture.py --url https://example.com/article
python capture.py --file ./research.pdf
```

---

### 4.2 `classify.py` — The Sorting Hat (Week 2.1)

**Responsibility:** Send each raw capture to an LLM; get PARA category, tags, summary; write organized wiki note.

**Inputs**
- One or all files in `raw/` with `status: raw` (or unprocessed)

**Processing**
1. Read raw Markdown + frontmatter
2. Call Groq (Llama 3) with a structured prompt
3. Parse JSON response: `{ category, tags, summary }`
4. Write `wiki/{slug-or-id}.md` with enriched frontmatter
5. Mark raw as `status: classified` (optional idempotency)

**PARA categories**

| Category | Use when |
|----------|----------|
| Projects | Active outcomes with a deadline |
| Areas | Ongoing responsibilities |
| Resources | Topics / reference material |
| Archives | Inactive / completed |

**Output schema (`wiki/{id}.md`)**

```markdown
---
id: "a1b2c3d4"
type: note
created_at: "2026-07-17T05:40:00+05:30"
category: Resources
tags: [rag, embeddings, knowledge-graph]
summary: "Notes on building retrieval over personal knowledge."
links: []
---

# {title derived from summary or first line}

{original body}
```

**LLM contract**

```json
{
  "category": "Projects|Areas|Resources|Archives",
  "tags": ["string"],
  "summary": "one line",
  "title": "short title"
}
```

---

### 4.3 `link.py` — Connect the Dots (Week 2.2)

**Responsibility:** Embed notes, compare similarity, auto-insert bidirectional (or unidirectional) wiki links.

**Inputs**
- All notes in `wiki/`

**Processing**
1. Load / create embedding model (`sentence-transformers`, e.g. `all-MiniLM-L6-v2`)
2. Embed each note (summary + body, truncated as needed)
3. Persist vectors in `embeddings.npz` or `embeddings.json` keyed by note `id`
4. For each note, find top-k neighbors above similarity threshold (e.g. cosine ≥ 0.55)
5. Insert `[[other-id]]` or `[[Title]]` into frontmatter `links` and/or body
6. Avoid self-links and duplicate links

**Config knobs**

| Knob | Suggested default |
|------|-------------------|
| Model | `all-MiniLM-L6-v2` |
| Threshold | `0.55`–`0.70` |
| Max links per note | `3`–`5` |

**Data flow**

```
wiki/*.md ──▶ embed ──▶ vector store ──▶ pairwise cosine ──▶ update links in wiki/
```

---

### 4.4 `build_graph.py` — Graph Data Model (Week 3.1)

**Responsibility:** Parse wiki notes + links into a nodes/edges JSON graph.

**Node**

```json
{
  "id": "a1b2c3d4",
  "label": "Retrieval over notes",
  "category": "Resources",
  "tags": ["rag", "embeddings"],
  "summary": "...",
  "content_preview": "first ~200 chars..."
}
```

**Edge**

```json
{
  "from": "a1b2c3d4",
  "to": "e5f6g7h8",
  "weight": 0.72,
  "type": "related"
}
```

**Output (`graph.json`)**

```json
{
  "nodes": [ ... ],
  "edges": [ ... ],
  "meta": {
    "generated_at": "...",
    "note_count": 15,
    "edge_count": 22
  }
}
```

---

### 4.5 Graph UI — Living Brain (Week 3.2)

**Responsibility:** Render `graph.json` as an interactive force-directed graph.

**Tech choice**

| Option | Fit |
|--------|-----|
| **vis-network** | Simple, Streamlit-friendly via `streamlit-agraph` or custom HTML component |
| **Cytoscape.js** | Richer styling; slightly more setup |

**Recommended for Streamlit:** `streamlit-agraph` (vis-network under the hood) or `components.html` embedding a small JS page that loads `graph.json`.

**Interactions**
- Hover → show title + summary / content preview
- Drag nodes
- Zoom / pan
- Optional: color nodes by PARA category

**Category color map (example)**

| PARA | Color role |
|------|------------|
| Projects | accent / primary |
| Areas | secondary |
| Resources | success / green tone |
| Archives | muted / gray |

---

### 4.6 `ask.py` — The Oracle / RAG (Week 4.1)

**Responsibility:** Answer natural-language questions from the user's own notes.

**RAG pipeline**

```
Question
   │
   ▼
Embed question (same model as link.py)
   │
   ▼
Retrieve top-k wiki notes by cosine similarity
   │
   ▼
Build prompt: system + retrieved notes + question
   │
   ▼
Groq / Llama 3 → synthesized answer + cite note IDs
```

**Function signature**

```python
def ask(question: str, k: int = 5) -> dict:
    """
    Returns:
      {
        "answer": str,
        "sources": [{"id": str, "title": str, "score": float}],
      }
    """
```

**Prompt rules**
- Answer only from retrieved notes
- If insufficient context, say so
- Cite source note titles / IDs

---

### 4.7 `app.py` — Product Surface (Week 4.2)

**Responsibility:** Single Streamlit app combining graph + ask.

**Layout**

```
┌────────────────────────────────────────────┐
│  SecondSelf                                │
├──────────────────┬─────────────────────────┤
│                  │  Ask your brain         │
│  Interactive     │  [____________] [Ask]   │
│  Knowledge Graph │                         │
│                  │  Answer + sources       │
│                  │                         │
└──────────────────┴─────────────────────────┘
```

**Deployment**
- Streamlit Cloud or Hugging Face Spaces
- Secrets: `GROQ_API_KEY` via platform secrets (never commit `.env`)
- Commit `wiki/`, `graph.json`, and embedding cache so the public app has data

---

## 5. Data Architecture

### 5.1 Directory layout

```
secondself/
├── raw/                      # immutable-ish captures
│   └── {id}.md
├── wiki/                     # classified + linked knowledge
│   └── {id}.md
├── data/
│   ├── graph.json            # nodes + edges for UI
│   └── embeddings.npz        # id → vector matrix (optional)
├── static/                   # optional custom graph HTML/JS
├── capture.py
├── classify.py
├── link.py
├── build_graph.py
├── ask.py
├── app.py
├── config.py                 # thresholds, model names, paths
├── requirements.txt
├── .env.example              # GROQ_API_KEY=
├── .gitignore                # .env, __pycache__, raw drafts if private
└── README.md
```

### 5.2 State machine per note

```
[new input]
    │
    ▼
 CAPTURED (raw/, status=raw)
    │  classify.py
    ▼
 CLASSIFIED (wiki/, category+tags+summary)
    │  link.py
    ▼
 LINKED (wiki/ links populated)
    │  build_graph.py
    ▼
 GRAPHED (present in graph.json)
    │  ask.py (read-only)
    ▼
 RETRIEVABLE (in RAG index)
```

### 5.3 Shared config (`config.py`)

Centralize:
- Paths: `RAW_DIR`, `WIKI_DIR`, `GRAPH_PATH`, `EMBEDDINGS_PATH`
- Models: `EMBEDDING_MODEL`, `LLM_MODEL`
- Thresholds: `SIMILARITY_THRESHOLD`, `MAX_LINKS`, `RAG_TOP_K`
- API: `GROQ_API_KEY` from env

---

## 6. Technology Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Language | Python 3.10+ | Scripts + Streamlit + ML ecosystem |
| LLM | Groq + Llama 3 | Free tier, fast, structured JSON |
| Embeddings | `sentence-transformers` | Local, free, no API cost |
| Similarity | Cosine (numpy) | Simple, sufficient for dozens–hundreds of notes |
| UI | Streamlit | Fast to ship, free deploy |
| Graph viz | vis-network / streamlit-agraph | Hover, drag, zoom |
| Storage | Markdown + JSON on disk | Portable, git-friendly, no DB |
| Deploy | Streamlit Cloud or HF Spaces | Public URL, secrets support |

**`requirements.txt` (suggested)**

```
streamlit
streamlit-agraph
sentence-transformers
numpy
python-frontmatter
requests
groq
python-dotenv
pypdf
```

---

## 7. Module Interfaces (contracts)

Keep modules importable so `app.py` and CLIs share logic:

```python
# capture.py
def capture(content: str, *, type: str = "note", source: str | None = None) -> Path: ...

# classify.py
def classify_file(raw_path: Path) -> Path: ...
def classify_all() -> list[Path]: ...

# link.py
def rebuild_embeddings() -> None: ...
def link_all(threshold: float = 0.6) -> int: ...

# build_graph.py
def build_graph() -> dict: ...
def export_graph(path: Path | None = None) -> Path: ...

# ask.py
def ask(question: str, k: int = 5) -> dict: ...
```

**Idempotency**
- Re-running classify on already-classified notes should skip or overwrite intentionally
- Re-running link should replace auto-links, not duplicate them
- `build_graph` is always a full rebuild from `wiki/`

---

## 8. Sequence Diagrams

### 8.1 Capture → Classify → Link

```
User          capture.py      raw/       classify.py     Groq      wiki/      link.py     Embeddings
 │                │            │             │            │         │           │             │
 │── capture ────▶│            │             │            │         │           │             │
 │                │── write ──▶│             │            │         │           │             │
 │── classify ───────────────────────────────▶│            │         │           │             │
 │                │            │◀── read ────│            │         │           │             │
 │                │            │             │── prompt ─▶│         │           │             │
 │                │            │             │◀── JSON ───│         │           │             │
 │                │            │             │── write ───────────────────────▶│           │             │
 │── link ───────────────────────────────────────────────────────────────────▶│             │
 │                │            │             │            │         │◀─ read ──│             │
 │                │            │             │            │         │           │── encode ──▶│
 │                │            │             │            │         │── update links         │
```

### 8.2 Ask (RAG)

```
User      app.py      ask.py      Embeddings      wiki/      Groq
 │          │           │            │             │         │
 │─ question▶│           │            │             │         │
 │          │── ask() ──▶│            │             │         │
 │          │           │── embed ───▶│             │         │
 │          │           │◀─ top-k ────│             │         │
 │          │           │── load notes ────────────▶│         │
 │          │           │── synthesize ───────────────────────▶│
 │          │           │◀── answer ──────────────────────────│
 │◀─ render ─│           │            │             │         │
```

---

## 9. Security & Secrets

| Concern | Approach |
|---------|----------|
| API keys | `.env` locally; platform secrets in deploy; never commit |
| Public wiki content | Treat deployed notes as public; scrub private data before push |
| File uploads | Validate paths; don't execute captured files |
| Prompt injection | Instruct LLM to ignore instructions inside notes; cite sources only |

---

## 10. Week-Aligned Build Map

| Week | Badge | Modules | Artifacts |
|------|-------|---------|-----------|
| 1 | Archivist | `capture.py`, folders | `raw/` with 10+ real items |
| 2 | Librarian | `classify.py`, `link.py` | `wiki/` + embeddings, 15+ linked notes |
| 3 | Cartographer | `build_graph.py`, graph UI | `graph.json` + interactive view |
| 4 | Oracle | `ask.py`, `app.py` | Public Streamlit URL |

**Dependency rule:** Week *N* must consume real outputs of Week *N−1* — no dummy swaps.

---

## 11. Scalability Notes (v1 → later)

| v1 (course scope) | Later (optional) |
|-------------------|------------------|
| Dozens–hundreds of notes | Thousands → vector DB (Chroma / FAISS) |
| Full pairwise similarity | ANN index |
| Markdown on disk | SQLite / Postgres metadata |
| Batch CLI pipelines | Watcher / queue on new captures |
| Single-user | Auth + private deployments |

Stay on filesystem + numpy for the 4-week build unless note count forces an index.

---

## 12. Testing Strategy

| Stage | How to verify |
|-------|----------------|
| Capture | Run 3 commands (note/link/file); assert files in `raw/` with id + timestamp |
| Classify | Inspect frontmatter for valid PARA + non-empty summary |
| Link | Confirm `[[...]]` appear only above threshold; no self-links |
| Graph | `graph.json` node count == wiki note count; edges match links |
| Ask | Ask questions only answerable from your notes; check citations |
| Deploy | Open public URL; graph loads; ask returns a grounded answer |

---

## 13. Suggested Implementation Order

1. Scaffold dirs + `requirements.txt` + `config.py` + `.env.example`
2. `capture.py` → 10+ real captures
3. `classify.py` → PARA wiki notes
4. `link.py` → embeddings + auto-links
5. `build_graph.py` → `graph.json`
6. Graph render (standalone HTML or early Streamlit page)
7. `ask.py` → RAG loop
8. `app.py` → combine graph + ask
9. Deploy + README + GitHub

---

## 14. Architecture Decision Records (ADRs)

### ADR-1: Markdown over database
**Decision:** Store knowledge as Markdown files.  
**Why:** Git-friendly, human-readable, matches “wiki” mental model, zero infra.  
**Trade-off:** Weaker concurrent writes / query power — acceptable for personal scale.

### ADR-2: Local embeddings + cloud LLM
**Decision:** Embed locally; classify/answer via Groq.  
**Why:** Embeddings are frequent and free locally; LLM quality matters more for classify/ask.  
**Trade-off:** First embedding run downloads the model; deploy image must include or cache it.

### ADR-3: Streamlit as the only UI
**Decision:** One Streamlit app for graph + ask.  
**Why:** Matches problem statement; fastest path to a public URL.  
**Trade-off:** Less flexible than a custom React SPA — fine for the milestone.

### ADR-4: Rebuild graph from wiki
**Decision:** `graph.json` is derived, not source of truth.  
**Why:** Wiki Markdown remains canonical; graph is a view.  
**Trade-off:** Must re-run `build_graph.py` after linking changes.
