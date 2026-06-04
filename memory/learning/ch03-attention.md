# Ch03 — Attention Mechanisms
*Captured: 2026-05-01 | Source: LLMs from Scratch, Chapter 3*

## The core idea

Attention is the thing that made modern LLMs possible. Before attention (pre-2017), models processed text left to right and struggled to connect words far apart in a sentence. Attention lets the model look at ALL tokens simultaneously and decide which ones are relevant to each other.

The mechanism works like a query/key/value lookup:
- **Query (Q):** "What am I looking for?" (the current token asking a question)
- **Key (K):** "What do I contain?" (every other token advertising its content)
- **Value (V):** "What do I actually contribute?" (the information to pass forward)

The model computes how much each token's key matches the current query, turns those into weights (via softmax), then takes a weighted sum of all the values. High attention weight = that token matters a lot for this prediction.

## Multi-head attention

Instead of doing this once, the model does it many times in parallel (multiple "heads"), each learning to pay attention to different relationships — one head might track grammar, another might track topic, another might track who's speaking. The results get combined.

## Causal (masked) attention

During training, the model can't "cheat" by looking at future tokens. A mask is applied so each token can only attend to tokens before it. This is what makes it a language *generator* — it has to predict forward without peeking.

## Why this matters for Bolt

This is the actual mechanism that makes OpenAI useful. When you send Bolt's memory as context, attention is what lets GPT connect a fact from MEMORY.md to a question asked three paragraphs later. The model isn't searching a database — it's computing attention weights across every token in context simultaneously.

Understanding this explains:
- Why longer, clearer prompts work better (more relevant tokens for attention to find)
- Why putting important info at the start OR end of a prompt works better than the middle (attention patterns have documented biases)
- Why Bolt_Memory loads the "hot cache" first — highest priority facts get the best attention position

## Key vocab

| Term | Plain meaning |
|------|---------------|
| Attention | Mechanism for tokens to "look at" each other and decide relevance |
| Self-attention | Each token attending to all other tokens in the same sequence |
| Multi-head attention | Running attention multiple times in parallel, each head learning different patterns |
| Softmax | Converts raw scores into weights that sum to 1 (probabilities) |
| Causal mask | Prevents tokens from attending to future tokens during training |
| Attention weight | How much one token "pays attention" to another (0 to 1) |

## Connected files in Bolt
- `modules/Bolt_Memory.py` — the memory context is what GPT runs attention over
- `modules/Think_Learn_Decide.py` — uses OpenAI (attention-powered) to make decisions about clips
- `neural_model.py` — the linear layers in your neural net are the precursor concept; attention adds the "look at everything at once" superpower
