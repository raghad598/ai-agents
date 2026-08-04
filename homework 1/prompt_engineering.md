### Prompt Engineering Concepts

Use this file to explain 3 different prompt engineering concepts that you tried and their effectiveness.

---

## 1. Role Prompting

**What it is:** Telling the model who it is before telling it what to do. Every expert in this system starts with the same sentence pattern — `You are a {{ role }}, an expert in {{ domain }}` — filled in differently per expert from the `llm_roles` table.

**How I used it:** All four experts share one underlying model (`openai/gpt-4o-mini`) and one master template. The only thing separating a Database Read Expert from a Content Expert is the role and domain strings rendered into the system prompt.

**Effectiveness:** This was the cheapest change with the biggest effect. Assigning the role alone shifted the model's default output style — the Read Expert stopped producing conversational answers and started producing query-shaped output before I had even added examples. It sets the register, but on its own it doesn't guarantee the *format*; that needed the next two techniques.

---

## 2. Output Format Constraints (Negative Instructions)

**What it is:** Explicitly stating what the output must *not* contain, not just what it should contain. My Read Expert's instructions say: *"Respond with a single valid SQLite SELECT query only. No markdown, no explanation — SQL only."*

**How I used it:** Both database experts get an explicit prohibition on markdown and prose. This matters because their output isn't shown to the user — it's passed straight to `db.query()` or `exec()`. A single stray code fence would make the SQL unparseable and the request would fail.

**Effectiveness:** Very effective, and necessary. Without the negative instruction, the model's habit is to wrap code in markdown fences and add a friendly sentence explaining what it did — helpful for a human reader, fatal for code that gets executed. Naming the unwanted behavior directly worked better than only describing the wanted one. I also added a guard in `execute_read_query()` that rejects anything not starting with `SELECT`, because prompt instructions reduce bad output but don't eliminate it.

---

## 3. Few-Shot Examples

**What it is:** Showing the model one worked example of the input-to-output transformation instead of only describing it. Each expert config has a `few_shot_examples` field with a single request-and-response pair.

**How I used it:** The Read Expert's example shows a duration question mapping to a `SELECT` with a `JOIN` between `positions` and `institutions`. The Orchestrator's example shows a compound request mapping to a two-element list with the Read Expert called before the Write Expert.

**Effectiveness:** The strongest of the three, and the most visible in testing. When I asked *"How long did they work at Massachusetts Institute of Technology?"*, the generated SQL matched the structure of my example almost exactly — same JOIN, same column selection, only the institution name changed. The Orchestrator's two-step plan for my compound request likewise mirrored the ordering in its example. One example carried more of the behavior than several sentences of instruction did.

---

## What I Learned About the Limits

Prompt engineering shaped the output reliably, but it didn't make the model *understand* the domain. Testing the compound request *"Does she know Rust? If not, add it..."*, the Read Expert generated a query with `WHERE e.name = 'she'` — it had treated the pronoun "she" as an experience name.

The SQL was syntactically perfect and structurally identical to my few-shot example, so the format instructions worked exactly as intended. What failed was reference resolution, which no amount of formatting guidance addresses. The query returned nothing, the Orchestrator concluded Rust wasn't listed, and the write step ran anyway — so the right thing happened by coincidence, not by correctness.

That's the boundary: these techniques control *shape*, not *comprehension*.