Your prompt engineering isn't the reason your LLM writes bad SQL.
Your metadata is.

Most teams dump raw DDL into the context window and wonder why their LLM
hallucinates joins, misses implicit foreign keys, and picks the wrong column
out of 400.

So they add more prompt instructions. More guardrails. More retries.

They're optimizing the wrong layer.

Better SQL starts with better context — not a better prompt.

Here's what actually moves the needle:

→ Enrich your schema with column stats (cardinality, nulls, distributions)
→ Infer the implicit foreign keys your DDL doesn't declare
→ Retrieve only the relevant tables — not the full schema dump

I built an open-source tool that does exactly this.
118 tests. Zero required dependencies. Python + CLI.

It gives the LLM the retrieval and augmentation layer
that most text-to-SQL pipelines skip entirely.
You bring your own model. It brings the context your model is missing.

Repo link in the first comment.

What's the dumbest SQL your LLM has ever generated because of bad context?
I'll go first in the comments.

#TextToSQL #PromptEngineering #OpenSource #DataEngineering #RAG

---

## First Comment (publish immediately after posting)

Here's the repo: [LINK TO GITHUB REPO]

SQLens is an open-source schema intelligence layer for text-to-SQL pipelines.
It enriches your database metadata before it reaches the LLM —
supports SQLite, PostgreSQL, MySQL, and BigQuery.

Star it if you want to follow development. PRs welcome.

I'll share my worst LLM-generated SQL story here too — [write your story].
