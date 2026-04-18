# SQLens Integration Examples

These examples show how to use SQLens with popular LLM frameworks.

## LangChain

```bash
pip install sqlens langchain langchain-openai
export OPENAI_API_KEY="your-key"
python examples/langchain_integration.py
```

## LlamaIndex

```bash
pip install sqlens llama-index llama-index-llms-openai
export OPENAI_API_KEY="your-key"
python examples/llamaindex_integration.py
```

Both examples work without API keys — they will show the enriched schema context that SQLens generates, which is the core value. The LLM call is optional to demonstrate the full pipeline.
