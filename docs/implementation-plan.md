# SecondSelf — Phase-Wise Implementation Plan

> Build order derived from [Problem Statement.md](./Problem%20Statement.md) and [Architecture.md](./Architecture.md).  
> Rule: each phase consumes **real outputs** of the previous phase — no dummy data swaps.

---

## Overview

| Phase | Name | Badge | Duration | Primary artifacts |
|-------|------|-------|----------|-------------------|
| 0 | Foundation | — | Day 0–1 | Repo scaffold, config, deps |
| 1 | Capture Pipeline | The Archivist | Week 1 | `raw/` with 10+ real items |
| 2 | Self-Organizing Wiki | The Librarian | Week 2 | `wiki/` + embeddings, 15+ linked notes |
| 3 | Living Brain | The Cartographer | Week 3 | `graph.json` + interactive graph |
| 4 | Ask + Ship | The Oracle | Week 4 | Streamlit app + public URL |
| 5 | Polish & Handoff | — | End of Week 4 | README, GitHub, final checklist |

```
Phase 0 ──▶ Phase 1 ──▶ Phase 2 ──▶ Phase 3 ──▶ Phase 4 ──▶ Phase 5
 scaffold    capture     classify     graph        RAG +      docs +
             pipeline    + link       + UI         deploy     ship
```

---

## Phase 0 — Foundation (Scaffold)

**Goal:** Empty but runnable project skeleton so every later script shares paths and config.

### Tasks

| # | Task | Details |
|---|------|---------|
| 0.1 | Create directory layout | `raw/`, `wiki/`, `data/`, `static/` (optional) |
| 0.2 | Add `requirements.txt` | `streamlit`, `streamlit-agraph`, `sentence-transformers`, `numpy`, `python-frontmatter`, `requests`, `groq`, `python-dotenv`, `pypdf` |
| 0.3 | Add `config.py` | Paths (`RAW_DIR`, `WIKI_DIR`, `GRAPH_PATH`, `EMBEDDINGS_PATH`), models, thresholds (`SIMILARITY_THRESHOLD`, `MAX_LINKS`, `RAG_TOP_K`) |
| 0.4 | Secrets hygiene | `.env.example` with `GROQ_API_KEY=`; `.gitignore` for `.env`, `__pycache__/`, model caches |
| 0.5 | Placeholders | Empty `.gitkeep` in `raw/` and `wiki/` so folders commit |
| 0.6 | Init git (optional) | Local repo ready; do not commit secrets |

### Exit criteria

- [ ] Folders exist: `raw/`, `wiki/`, `data/`
- [ ] `pip install -r requirements.txt` succeeds in a venv
- [ ] `config.py` imports without error
- [ ] `.env` is gitignored; `.env.example` is committed

### Deliverable

Runnable scaffold. No product features yet.

---

## Phase 1 — The Archivist: Capture Everything, Lose Nothing

**Goal:** One command captures a note, link, or file into `raw/` with timestamp + unique ID.

**Depends on:** Phase 0  
**Problem ref:** Week 1  
**Architecture ref:** §4.1 Capture

### Tasks

| # | Task | Details |
|---|------|---------|
| 1.1 | Implement `capture()` | Generate UUID/ULID + ISO timestamp; detect type `note` \| `link` \| `file` |
| 1.2 | Write raw Markdown schema | Frontmatter: `id`, `type`, `created_at`, `source`, `status: raw` + body |
| 1.3 | Note capture path | CLI: `python capture.py "free text idea"` |
| 1.4 | Link capture path | CLI: `python capture.py --url https://...` (store URL + optional title fetch) |
| 1.5 | File capture path | CLI: `python capture.py --file path.pdf`; extract text (txt/md/pdf via `pypdf`); keep `source` path |
| 1.6 | CLI entrypoint | `argparse` / click-style interface; print saved path on success |
| 1.7 | Real-data soak | Capture **10+ real** notes/links/files from your own life — not fixtures |

### Suggested order of work

1. Schema + `capture()` for plain notes  
2. Link + file branches  
3. Wire CLI  
4. Capture 10+ real items  

### Acceptance criteria (ship gate)

- [ ] `raw/` and `wiki/` folder structure exists
- [ ] One command captures a **note**, a **link**, AND a **file**
- [ ] Every capture has a **timestamp + unique ID**
- [ ] **10+ real items** in `raw/`

### Verification

```bash
python capture.py "Test idea about RAG"
python capture.py --url https://example.com
python capture.py --file ./some-local.pdf
# Inspect raw/*.md — id, created_at, type, body present
```

### Deliverable

**Badge: The Archivist** — working capture pipeline + populated `raw/`.

### Do not start Phase 2 until

`raw/` has ≥10 real captures with valid frontmatter.

---

## Phase 2 — The Librarian: Teach AI to Organize For You

**Goal:** Auto-classify with PARA and auto-link related notes via embeddings.

**Depends on:** Phase 1 (`raw/` populated)  
**Problem ref:** Week 2  
**Architecture ref:** §4.2 Classify, §4.3 Link

Split into two sub-phases so classify works before embeddings.

---

### Phase 2A — Auto-Classify (The Sorting Hat)

| # | Task | Details |
|---|------|---------|
| 2A.1 | Groq client setup | Load `GROQ_API_KEY` from `.env`; pick Llama 3 model in `config.py` |
| 2A.2 | Classification prompt | Request JSON: `{ category, tags, summary, title }` with PARA constraints |
| 2A.3 | Implement `classify_file()` | Read `raw/*.md` → LLM → write `wiki/{id}.md` |
| 2A.4 | Wiki frontmatter | `category`, `tags`, `summary`, `links: []` + title heading + original body |
| 2A.5 | Implement `classify_all()` | Batch unprocessed raw files; skip or overwrite intentionally (idempotent) |
| 2A.6 | Mark progress | Optional: set raw `status: classified` |
| 2A.7 | Run on real data | Classify all Phase 1 captures; spot-check PARA quality |

**2A exit criteria**

- [ ] Any raw capture → category + tags + summary automatically  
- [ ] PARA categories only: Projects / Areas / Resources / Archives  
- [ ] `wiki/` contains classified notes from real captures  

---

### Phase 2B — Auto-Link (Connect the Dots)

| # | Task | Details |
|---|------|---------|
| 2B.1 | Load embedding model | `sentence-transformers` e.g. `all-MiniLM-L6-v2` |
| 2B.2 | `rebuild_embeddings()` | Embed summary + body per wiki note; save `data/embeddings.npz` (ids + matrix) |
| 2B.3 | Similarity | Cosine similarity; config threshold (start `0.55`–`0.70`) |
| 2B.4 | `link_all()` | Top-k neighbors above threshold; max links per note (`MAX_LINKS`) |
| 2B.5 | Write links | Update frontmatter `links` and/or body `[[id]]` / `[[Title]]`; no self-links; no duplicates |
| 2B.6 | Re-run safety | Replacing auto-links on re-run must not stack duplicates |
| 2B.7 | Scale data | Grow to **15+ real** wiki notes (capture more if needed, then classify + link) |

**2B exit criteria**

- [ ] Embeddings computed per note  
- [ ] Related notes auto-linked (no manual tagging)  
- [ ] Runs on **15+ real items** → organized linked `wiki/`  

### Acceptance criteria (ship gate)

- [ ] Any raw capture → category + tags + summary automatically
- [ ] PARA categorization working
- [ ] Embeddings computed per note
- [ ] Related notes auto-linked (no manual tagging)
- [ ] Runs on 15+ real items → organized `wiki/`

### Verification

```bash
python classify.py          # or classify_all()
python link.py              # rebuild embeddings + link_all()
# Spot-check wiki frontmatter: category in PARA, links non-empty for related pairs
```

### Deliverable

**Badge: The Librarian** — self-organizing wiki pipeline.

### Do not start Phase 3 until

`wiki/` has ≥15 linked real notes and embeddings file exists.

---

## Phase 3 — The Cartographer: Visualize the Brain

**Goal:** Turn wiki links into `graph.json` and an interactive force-directed graph.

**Depends on:** Phase 2 (`wiki/` linked)  
**Problem ref:** Week 3  
**Architecture ref:** §4.4 Build Graph, §4.5 Graph UI

---

### Phase 3A — Graph Data Model

| # | Task | Details |
|---|------|---------|
| 3A.1 | Parse wiki notes | Read frontmatter + `[[links]]` from every file |
| 3A.2 | Build nodes | `id`, `label`, `category`, `tags`, `summary`, `content_preview` |
| 3A.3 | Build edges | `from`, `to`, `weight` (similarity if available), `type: related` |
| 3A.4 | `build_graph()` / `export_graph()` | Always full rebuild from `wiki/` → `data/graph.json` |
| 3A.5 | Meta block | `generated_at`, `note_count`, `edge_count` |

**3A exit criteria**

- [ ] Script builds nodes + edges and exports clean JSON  
- [ ] Node count == wiki note count  
- [ ] Edges match declared links  

---

### Phase 3B — Interactive Graph UI

| # | Task | Details |
|---|------|---------|
| 3B.1 | Choose renderer | Prefer `streamlit-agraph` (vis-network) for later Phase 4 merge |
| 3B.2 | Load `graph.json` | Map nodes/edges into library format |
| 3B.3 | Interactions | Hover → title + summary/preview; drag; zoom/pan |
| 3B.4 | Visual encoding | Color nodes by PARA category (Projects / Areas / Resources / Archives) |
| 3B.5 | Smoke UI | Temporary Streamlit page or HTML that proves graph works on **real** notes |

**3B exit criteria**

- [ ] Interactive force-directed graph renders from JSON  
- [ ] Hover reveals note content  
- [ ] Drag + zoom work  
- [ ] Built from real notes, not dummy data  

### Acceptance criteria (ship gate)

- [ ] Script builds nodes + edges from notes and exports clean JSON
- [ ] Interactive force-directed graph renders from that JSON
- [ ] Hover reveals note content
- [ ] Drag + zoom work
- [ ] Built from your real notes, not dummy data

### Verification

```bash
python build_graph.py
# Open graph UI; hover several nodes; drag + zoom
# Confirm counts match wiki/
```

### Deliverable

**Badge: The Cartographer** — living interactive brain.

### Do not start Phase 4 until

`data/graph.json` is valid and graph UI works on real data.

---

## Phase 4 — The Oracle: Ask It Anything, Ship It Public

**Goal:** RAG over your notes + one Streamlit product + public URL.

**Depends on:** Phase 3 (graph) + Phase 2 (embeddings + wiki)  
**Problem ref:** Week 4  
**Architecture ref:** §4.6 Ask, §4.7 App

---

### Phase 4A — Natural Language Search (RAG)

| # | Task | Details |
|---|------|---------|
| 4A.1 | Implement `ask(question, k=5)` | Embed question → top-k wiki notes → Groq synthesize |
| 4A.2 | Prompt rules | Answer only from retrieved notes; admit gaps; cite note IDs/titles |
| 4A.3 | Return contract | `{ answer, sources: [{ id, title, score }] }` |
| 4A.4 | Reuse embeddings | Same model + store as `link.py` (do not train a second index) |
| 4A.5 | CLI smoke test | `python ask.py "What did I save about X?"` against real questions |

**4A exit criteria**

- [ ] `ask()` returns answers synthesized from your own notes  
- [ ] Sources list is non-empty when relevant notes exist  

---

### Phase 4B — UI + Deployment

| # | Task | Details |
|---|------|---------|
| 4B.1 | Assemble `app.py` | Left/main: interactive graph; right/side: ask bar + answer + sources |
| 4B.2 | Wire modules | Import `ask()` and load `graph.json`; no duplicated business logic |
| 4B.3 | Local run | `streamlit run app.py` — graph + ask both work |
| 4B.4 | Prep deploy data | Commit scrubbed `wiki/`, `data/graph.json`, embeddings (or rebuild on boot if feasible) |
| 4B.5 | Platform secrets | Set `GROQ_API_KEY` in Streamlit Cloud or HF Spaces — never in git |
| 4B.6 | Deploy | Streamlit Cloud **or** Hugging Face Spaces → public URL |
| 4B.7 | E2E on URL | Open public link; graph loads; ask returns grounded answer |

**4B exit criteria**

- [ ] One Streamlit app contains graph + search bar  
- [ ] Deployed live with a public URL  
- [ ] Full pipeline works end-to-end in the deployed app  

### Acceptance criteria (ship gate)

- [ ] `ask()` returns answers synthesized from your own notes (retrieval + LLM)
- [ ] One Streamlit app contains both the graph and the search bar
- [ ] Deployed live with a public URL
- [ ] Full pipeline works end to end in the deployed app

### Verification

```bash
python ask.py "Summarize what I know about <topic from my notes>"
streamlit run app.py
# After deploy: open public URL; ask the same question; check citations
```

### Deliverable

**Badge: The Oracle** — SecondSelf live.

---

## Phase 5 — Polish & Handoff

**Goal:** Project is reproducible and demo-ready.

**Depends on:** Phase 4 public URL

### Tasks

| # | Task | Details |
|---|------|---------|
| 5.1 | README | Setup, `.env`, capture→classify→link→graph→ask flow, deploy notes |
| 5.2 | Public GitHub | Clean repo; no secrets; clear structure matching Architecture §5.1 |
| 5.3 | Final E2E checklist | Capture → classify → link → graph → ask verified once more |
| 5.4 | Demo script | 3–5 sample questions that showcase your real notes |
| 5.5 | Optional screenshots | Graph + ask answer for README |

### Final deliverables checklist

- [ ] Public GitHub repo with clean README + setup instructions
- [ ] Live deployed URL — interactive graph + ask-your-brain search, both working
- [ ] End-to-end flow verified: capture → classify → link → graph → ask
- [ ] All 4 weekly milestones complete (Capture Pipeline, Self-Organizing Wiki, Living Brain, SecondSelf deployment)

---

## Cross-Phase Rules

1. **Real data only** — every phase tested on your notes, not fixtures.  
2. **Wiki is canonical** — rebuild `graph.json` and embeddings; never treat them as source of truth.  
3. **Idempotent scripts** — re-running classify/link/graph must be safe (skip or replace, never duplicate junk).  
4. **Secrets stay out of git** — local `.env`; platform secrets in deploy.  
5. **Public content scrub** — anything pushed/deployed is treated as public.  
6. **Week N consumes Week N−1** — do not invent parallel dummy datasets.

---

## Dependency Graph (modules)

```
config.py
    │
    ├── capture.py ──────────────▶ raw/*.md
    │                                  │
    ├── classify.py ◀── Groq ──────────┘
    │         │
    │         ▼
    │      wiki/*.md
    │         │
    ├── link.py ◀── sentence-transformers
    │         │
    │         ├──▶ wiki/*.md (links updated)
    │         └──▶ data/embeddings.npz
    │                    │
    ├── build_graph.py ──┼──▶ data/graph.json
    │                    │
    ├── ask.py ◀─────────┘  (+ Groq)
    │         │
    └── app.py ◀── graph.json + ask() ──▶ Streamlit public URL
```

---

## Suggested Calendar (4 weeks)

| Week | Focus | Ship |
|------|--------|------|
| **Week 1** | Phase 0 + Phase 1 | Capture pipeline + 10+ raw items |
| **Week 2** | Phase 2A + 2B | Classified + linked wiki (15+) |
| **Week 3** | Phase 3A + 3B | `graph.json` + interactive graph |
| **Week 4** | Phase 4A + 4B + 5 | RAG + deployed SecondSelf + README |

Daily rhythm (recommended):

1. Implement the day’s task  
2. Run on **real** notes  
3. Check that phase’s acceptance boxes  
4. Commit working state before moving on  

---

## Risk Register & Mitigations

| Risk | Phase | Mitigation |
|------|-------|------------|
| Groq rate limits / key issues | 2, 4 | Cache classify results; retry with backoff; keep prompts short |
| Embedding model download large on deploy | 2, 4 | Pin model; document first-run time; consider pre-commit of embeddings only for ask |
| Weak auto-links (threshold too low/high) | 2B | Tune `SIMILARITY_THRESHOLD` on your corpus; cap `MAX_LINKS` |
| PDF text extraction poor | 1 | Fallback: store filename + manual note; support txt/md first |
| Streamlit graph lib friction | 3, 4 | Fallback: `components.html` + vis-network CDN |
| Private notes leaked | 4, 5 | Scrub before push; separate private `raw/` if needed |
| “It works locally, fails on cloud” | 4B | Pin deps; set secrets; commit required data files |

---

## Definition of Done (project)

SecondSelf is done when:

1. Capture, classify, link, graph, and ask all work on **your** notes.  
2. A **public URL** shows the interactive graph and answers grounded questions with sources.  
3. A stranger can clone the GitHub repo, follow the README, and reproduce the pipeline.  
4. All acceptance checklists in Phases 1–5 are checked.

---

## Quick command cheat sheet (target end state)

```bash
# Phase 1
python capture.py "my idea"
python capture.py --url https://...
python capture.py --file ./doc.pdf

# Phase 2
python classify.py
python link.py

# Phase 3
python build_graph.py

# Phase 4
python ask.py "What do I know about X?"
streamlit run app.py
```
