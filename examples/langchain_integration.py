"""SQLens + LangChain integration example.

Shows how to use SQLens to enrich database context and feed it
to a LangChain LLM chain for text-to-SQL generation.

Requirements:
    pip install sqlens langchain langchain-openai

Usage:
    export OPENAI_API_KEY="your-key-here"
    python examples/langchain_integration.py
"""

from __future__ import annotations

import os

from sqlens import SQLens


def main() -> None:
    # ── Step 1: Enrich schema with SQLens ────────────────────────
    # Use the bundled ecommerce fixture (or replace with your own DB)
    db_path = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "ecommerce.db")

    ctx = SQLens.from_sqlite(db_path)
    ctx.enrich(
        descriptions=True,  # rule-based column descriptions
        relations=True,     # infer implicit foreign keys
        domains=True,       # auto-tag business domains
    )

    # ── Step 2: Retrieve context for a natural-language query ────
    query = "What are the top 5 customers by total order amount?"

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

    # ── Step 3: Feed to LangChain ────────────────────────────────
    # This step requires: pip install langchain langchain-openai
    # and OPENAI_API_KEY set in environment.
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI
    except ImportError:
        print("=" * 60)
        print("LangChain not installed. The schema context above is what")
        print("you would pass to your LLM. Install langchain to see the")
        print("full integration:")
        print("  pip install langchain langchain-openai")
        return

    if not os.environ.get("OPENAI_API_KEY"):
        print("=" * 60)
        print("Set OPENAI_API_KEY to run the LangChain integration.")
        print("The schema context above is ready to use with any LLM.")
        return

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a SQL expert. Given the database schema context below, "
            "write a SQL query that answers the user's question.\n\n"
            "Schema context:\n{schema_context}\n\n"
            "Return ONLY the SQL query, no explanation."
        )),
        ("human", "{question}"),
    ])

    chain = prompt | llm

    response = chain.invoke({
        "schema_context": schema_context,
        "question": query,
    })

    print("=" * 60)
    print("GENERATED SQL (from LangChain + OpenAI)")
    print("=" * 60)
    print(response.content)


if __name__ == "__main__":
    main()
