# Ch02 — Working with Text Data
*Captured: 2026-05-01 | Source: LLMs from Scratch, Chapter 2*

## The core idea

Before an LLM can process text, text has to become numbers. That conversion happens in two steps:

1. **Tokenization** — Split text into chunks called tokens. Not always whole words — "running" might be one token, "unbelievable" might be split into "un", "believ", "able". GPT-2 uses Byte Pair Encoding (BPE), which builds a vocabulary by merging the most common character pairs repeatedly until you have ~50,000 tokens.

2. **Embeddings** — Each token ID gets mapped to a vector (a list of numbers, like 768 or 1024 floats). These vectors capture meaning — words with similar meanings end up near each other in vector space. "King" minus "man" plus "woman" approximately equals "Queen." That's not magic, that's what embeddings learn.

## What Billy built (neural_model.py connection)

The `neural_model.py` file already uses this structure — just simpler:
- Input is raw numbers (coordinates), not text
- But the pattern is identical: raw data → tensor → layers → output
- `DataLoader` and `Dataset` classes are the same ones LLMs use, just with different data inside

The jump from that toy example to a real LLM tokenizer is the same concept scaled up.

## Key vocab

| Term | Plain meaning |
|------|---------------|
| Token | One chunk of text the model sees at a time (word, part of word, punctuation) |
| Token ID | The number that represents that token in the vocabulary |
| Embedding | A list of numbers that captures the *meaning* of a token |
| Vocabulary | The full list of tokens the model knows (~50,257 for GPT-2) |
| BPE | Byte Pair Encoding — the algorithm that builds the vocabulary |
| Context window | How many tokens the model can see at once (GPT-2: 1024, Claude: much larger) |

## Why this matters for Bolt

Every time Bolt sends a prompt to Claude, Claude tokenizes it first. The length of prompts matters because tokens cost money and hit context limits. Long memory files = more tokens = higher API cost. This is why `Bolt_Memory.py` uses a "hot cache" (MEMORY.md) instead of dumping every file into every call — it keeps token count manageable.

## What Billy can do with this

- Estimate API costs by token count (roughly 1 token ≈ 0.75 words)
- Know why Bolt's memory system is designed the way it is
- Understand why Claude sometimes "forgets" early parts of long conversations (context window limit)
- When something costs too many tokens, now you know why

## Connected files in Bolt
- `modules/Bolt_Memory.py` — `load_all_memory()` manages token budget deliberately
- `modules/AI_Title_Generator.py` — sends prompts to Claude (tokens going in)
- `modules/Subtitle_Generator.py` — uses Whisper for transcription (similar input-as-tokens concept)
