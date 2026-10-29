# Job Application Agent — Design Document

**Student:** Raghad AbdulRahim
**Course:** CSE 491 — AI Agents
**Project:** Final Project

---

## 1. What is the project idea?

A multi-expert AI agent that takes a job posting and the user's own resume
database, and produces three things:

1. A **structured breakdown** of what the job actually requires
2. A **match score** showing how well the user fits, with the specific gaps named
3. A **tailored cover letter** that cites the user's real experiences

The core problem it solves: applicants either send one generic cover letter to
fifty jobs, or spend an hour tailoring each one. Neither works. The first gets
ignored; the second doesn't scale. This agent does the tailoring work in the
time it takes to paste a job posting.

The part that makes it more than a text generator is the **gap analysis**. Most
AI writing tools will happily claim you're a perfect fit for anything. This one
tells you what you're missing — which is the information you actually need when
deciding whether to apply at all.

---

## 2. How does it use an LLM Agent?

The system uses an **Orchestrator + specialist experts** architecture, extending
the pattern built in Homework 1 and 2.

The Orchestrator receives a request, decomposes it into an ordered plan of
expert calls, executes them in sequence, and synthesizes one reply. Order
matters: later experts depend on earlier results.

### The experts

| Expert | Responsibility |
|---|---|
| **Job Analysis Expert** | Reads a raw job posting, extracts requirements as a structured list |
| **Match Expert** | For each requirement, runs semantic search against the resume database; returns matches with similarity scores, and flags unmatched requirements as gaps |
| **Cover Letter Expert** | Writes a tailored letter citing only real experiences found by the Match Expert |
| **Database Read Expert** | Exact SQL queries (inherited from HW1) |
| **Database Semantic Search Expert** | Meaning-based search (inherited from HW2) |
| **Database Write Expert** | Saves applications (inherited from HW1) |
| **Content Expert** | Answers from visible page content (inherited from HW1) |

### Why semantic search is essential here

A job posting says "experience with machine learning frameworks." The resume
database says "Scikit-Learn." Exact SQL matching returns nothing. Embedding
similarity returns a strong match.

This is the same capability built in Homework 2, applied to a problem where it
is not a convenience but a requirement — job postings and resumes almost never
use the same vocabulary for the same skill.

### Human-in-the-loop

The validation gate from Homework 2 guards any destructive or outbound action:
deleting a saved application, or overwriting an existing cover letter. The
request pauses and asks for explicit confirmation before anything runs.

---

## 3. Who is this project designed for?

**Primary users:** recent graduates and students applying to many positions,
who need to tailor each application but don't have an hour per posting.

**Specifically useful for:**

- Applicants whose experience uses different vocabulary than the job posting
  (academic project names vs. industry skill names)
- Non-native English speakers who want a well-written letter grounded in their
  real history rather than invented claims
- Anyone deciding whether a given posting is worth applying to at all — the gap
  analysis answers that before the letter is written

---

## 4. Flow diagram of the technical design

```
                    User pastes a job posting
                               |
                               v
                    +----------------------+
                    |  Risk assessment     |   keyword scan, no AI call
                    |  (delete/remove/...) |
                    +----------------------+
                         |            |
                    risky|            |safe
                         v            v
              +------------------+   +------------------+
              | Ask user: yes/no |   |   ORCHESTRATOR   |
              +------------------+   +------------------+
                    |                         |
                yes |                         | builds ordered plan
                    +------------------------>|
                                              v
             +--------------------------------------------------+
             |                                                  |
             v                                                  |
    +--------------------+                                      |
    | Job Analysis Expert|  extracts requirements as a list      |
    +--------------------+                                      |
             |                                                  |
             v                                                  |
    +--------------------+                                      |
    |    Match Expert    |                                      |
    +--------------------+                                      |
             |                                                  |
             | for each requirement:                            |
             v                                                  |
    +--------------------+     +---------------------------+    |
    | generate_embedding |---->| cosine similarity vs rows |    |
    +--------------------+     +---------------------------+    |
             |                            |                     |
             |                            v                     |
             |                  +---------------------+         |
             |                  | skills, experiences |         |
             |                  | (SQLite + embedding)|         |
             |                  +---------------------+         |
             v                                                  |
    +------------------------------------------+                |
    | match score + matched rows + GAPS         |               |
    +------------------------------------------+                |
             |                                                  |
             v                                                  |
    +------------------------+                                  |
    | Cover Letter Expert    |  cites only matched experiences   |
    +------------------------+                                  |
             |                                                  |
             +------------------------------------------------->+
                                              |
                                              v
                                    +------------------+
                                    |   Synthesis      |
                                    +------------------+
                                              |
                                              v
                                    Reply shown to user
```

---

## 5. What data or information is needed?

### Database: yes — SQLite

The existing resume schema is reused unchanged:

| Table | Holds | Embedded on |
|---|---|---|
| `institutions` | Places studied or worked | name + department |
| `positions` | Job titles held | title + responsibilities |
| `experiences` | Specific projects | name + description |
| `skills` | Individual skills | name |

Each table carries an `embedding TEXT` column storing a JSON-encoded 1536-number
vector, generated via OpenRouter's `text-embedding-3-small`.

### One new table

```sql
CREATE TABLE IF NOT EXISTS applications (
    application_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    company         TEXT NOT NULL,
    role_title      TEXT NOT NULL,
    posting_text    TEXT NOT NULL,
    match_score     REAL,
    gaps            TEXT,          -- JSON list of unmatched requirements
    cover_letter    TEXT,
    created_at      TEXT NOT NULL
);
```

### Other models

**No VLM.** Job postings are text; adding vision would add cost and complexity
with no benefit. This is a deliberate scoping decision, not an omission.

**Embedding model:** `openai/text-embedding-3-small` via OpenRouter — the same
model and key used for chat, no separate credential needed.

---

## 6. Key components

| # | Component | Status |
|---|---|---|
| 1 | Orchestrator + expert routing | ✅ built (HW1) |
| 2 | SQLite resume database | ✅ built (HW1) |
| 3 | Embedding generation + storage | ✅ built (HW2) |
| 4 | Semantic search (cosine similarity) | ✅ built (HW2) |
| 5 | Human validation gate | ✅ built (HW2) |
| 6 | **Job Analysis Expert** | 🔨 new |
| 7 | **Match Expert + scoring logic** | 🔨 new — the core contribution |
| 8 | **Cover Letter Expert** | 🔨 new |
| 9 | **`applications` table** | 🔨 new |
| 10 | **Job posting input UI** | 🔨 new |

Five of ten components already exist and are tested. The project's new work
concentrates on components 6–10, with component 7 carrying most of the value.

---

## 7. Deadlines per component

| Block | Component | Deliverable |
|---|---|---|
| 1 | Copy HW2 → `final project`, add `applications` table | App runs, table exists |
| 2 | Job Analysis Expert | Pasting a posting returns a requirement list in console |
| 3 | Match Expert — per-requirement semantic search | Console prints each requirement with its best match + score |
| 4 | Match Expert — scoring + gap detection | Returns overall % and named gaps |
| 5 | Cover Letter Expert + input UI | End-to-end: paste posting → letter |
| 6 | Testing + demo video | Recorded |

**Scope rule:** anything not needed for a five-minute demo is cut. Saving
applications to the database is the first thing to drop if time runs short —
the match analysis and letter are the demonstrable value.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| API rate limits / credit exhaustion | Match Expert embeds each requirement once, not per database row; posting text is embedded once and reused |
| Slow network stalls the demo | Test all demo queries immediately before recording; console output is the primary evidence |
| Expert returns malformed output | Each executor wraps parsing in try/except and returns a safe message rather than crashing |
| Scope creep | Components 1–5 are already working; new work is deliberately limited to four experts and one table |
