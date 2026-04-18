"""SQLens + LlamaIndex integration example.

Shows how to use SQLens to enrich database context and feed it
to a LlamaIndex query engine for text-to-SQL generation.

Requirements:
    pip install sqlens llama-index llama-index-llms-openai

Usage:
    export OPENAI_API_KEY="your-key-here"
    python examples/llamaindex_integration.py
"""

from __future__ import annotations

import os

from sqlens import SQLens


def main() -> None:
    # ── Step 1: Enrich schema with SQLens ────────────────────────
    db_path = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "ecommerce.db")

    ctx = SQLens.from_sqlite(db_path)
    ctx.enrich(
        descriptions=True,
        relations=True,
        domains=True,
    )

    # ── Step 2: Retrieve context for a natural-language query ────
    query = "Which product categories have the highest return rate?"

    context = ctx.get_context(
        query,
        max_tables=5,
        level="standard",
        domain="auto",
    )

    schema_context = context.to_prompt()

    print("=" * 60)
    print("ENRICHED SCHEMA CONTEXT (from SQLens)")
    print("=" * 60)
    print(schema_context)
    print()

    # ── Step 3: Feed to LlamaIndex ───────────────────────────────
    # This step requires: pip install llama-index llama-index-llms-openai
    # and OPENAI_API_KEY set in environment.
    try:
        from llama_index.core.llms import ChatMessage
        from llama_index.llms.openai import OpenAI
    except ImportError:
        print("=" * 60)
        print("LlamaIndex not installed. The schema context above is what")
        print("you would pass to your LLM. Install llama-index to see the")
        print("full integration:")
        print("  pip install llama-index llama-index-llms-openai")
        return

    if not os.environ.get("OPENAI_API_KEY"):
        print("=" * 60)
        print("Set OPENAI_API_KEY to run the LlamaIndex integration.")
        print("The schema context above is ready to use with any LLM.")
        return

    llm = OpenAI(model="gpt-4o-mini", temperature=0)

    messages = [
        ChatMessage(
            role="system",
            content=(
                "You are a SQL expert. Given the database schema context below, "
                "write a SQL query that answers the user's question.\n\n"
                f"Schema context:\n{schema_context}\n\n"
                "Return ONLY the SQL query, no explanation."
            ),
        ),
        ChatMessage(role="user", content=query),
    ]

    response = llm.chat(messages)

    print("=" * 60)
    print("GENERATED SQL (from LlamaIndex + OpenAI)")
    print("=" * 60)
    print(response.message.content)


if __name__ == "__main__":
    main()
