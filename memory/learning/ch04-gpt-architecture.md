# Ch04 — Implementing a GPT Model from Scratch
*Captured: 2026-05-05 | Source: LLMs from Scratch, Chapter 4 (YouTube walkthrough + session with Bolt)*

## The core idea

Chapter 4 is where it all comes together — you build an actual GPT model from scratch, brick by brick. By the end you have something that can generate text (terrible text, since it's untrained, but *real* generated text using the same architecture as GPT-2).

The model is built from four main components stacked in layers:

1. **LayerNorm** — Normalizes the numbers flowing through the network so training stays stable. Without it, values blow up or collapse and the model can't learn.
2. **GELU activation** — A smoother version of ReLU. Instead of a hard cutoff at zero, it curves gently. This makes gradients flow better and gives the model more nuance.
3. **FeedForward block** — Two linear layers with a 4x expansion in the middle. Takes each token's attention output and transforms it through a bigger space, then back down. This is where individual token "thinking" happens (attention is about tokens relating to *each other*; FFN is each token processing on its *own*).
4. **Residual (shortcut) connections** — Adds the input back to the output at the end of each sub-block. This lets gradients flow all the way back through deep networks without vanishing. Think of it as a highway lane running alongside the main road — if the main road is congested, information can take the shortcut.

These four things get wrapped into a **TransformerBlock**, and you stack 12 of those blocks to get GPT-2 (124M parameter version).

## The full GPT architecture in order

```
Input tokens
    ↓
Token Embedding (50,257 vocab → 768 dimensions)
    +
Positional Embedding (1024 positions → 768 dimensions)
    ↓
[TransformerBlock × 12]
    Each block:
    → LayerNorm → Multi-Head Attention → Residual add
    → LayerNorm → FeedForward (768→3072→768) → Residual add
    ↓
Final LayerNorm
    ↓
Output projection (768 → 50,257)  ← predicts next token
```

## What I built / tried

Watched the chapter walkthrough. The code builds GPT step by step, starting with dummy placeholder classes that prove the shape is right before filling in the real implementations. Key moment: the untrained model outputs complete nonsense ("Hello, I am Featureiman Byeswickattribute argue...") — which is *correct behavior*. Random weights = random predictions. This is the starting point before training.

The model has 163M parameters total (124M when you tie the input/output weights together, which GPT-2 actually does).

## Key vocab

| Term | Plain meaning |
|------|---------------|
| LayerNorm | Rescales numbers mid-network so they don't blow up. Stability layer. |
| GELU | Activation function — smoother than ReLU, lets gradients flow better |
| FeedForward block | Each token processes itself through two linear layers (4x expanded middle) |
| Residual connection | Adds the original input back at the end of each block — keeps gradients flowing in deep networks |
| TransformerBlock | One full "layer" of the model: attention + feedforward, each with LayerNorm + residual |
| Weight tying | Sharing the same weight matrix for input embedding AND output projection — saves ~38M params |
| Greedy decoding | Text generation: always pick the highest-probability next token. Simple but repetitive. |
| Temperature | A dial on text generation: higher = more random, lower = more focused |
| Top-k sampling | Only sample from the top k most likely tokens — better text quality than pure greedy |

## Why this matters for Bolt

This is the architecture behind Claude. When Bolt sends context to Claude — memory files, chat history, clip metadata — those tokens go through exactly this structure. Knowing this changes how you think about prompts:

- **Residual connections** mean early information doesn't just disappear — it stays in the mix through all 12+ layers. Important context early in a prompt still matters at the end.
- **The FeedForward 4x expansion** is where "reasoning" happens at the token level. Richer prompts with more context give this layer more to work with.
- **LayerNorm** explains why Claude handles both short and long inputs without breaking — the normalization keeps everything in range regardless of input size.
- **Weight tying** is a hint at why Claude's input vocabulary and output vocabulary are the same thing — it's predicting tokens from the same space it reads them.

Practically: `modules/Think_Learn_Decide.py` and `modules/AI_Title_Generator.py` are calling Claude — which means they're firing this full architecture on every call. Every token in Bolt's memory context is going through 96 transformer blocks (Claude's architecture, much deeper than GPT-2's 12).

## What I can do with this now

- Look at `neural_model.py` and see the exact same pattern: linear layers, activations, stacking — just without attention. The GPT FeedForward block IS that neural net, embedded inside something bigger.
- Understand why Bolt's prompts should have structure: the attention mechanism needs clear signals. Vague prompts = noisy attention weights = worse outputs.
- Start thinking about what Chapter 5 covers: training. The untrained model is done — now the question is how do you actually teach it?
- The `neural_model.py` file moved to `llm/` this session — fitting, since it's now the foundation piece for understanding GPT's FFN blocks.

## Questions still open

- How does temperature sampling actually work in the softmax step? The chapter shows it but I want to understand the math of dividing logits by temperature.
- What does "pre-norm" vs "post-norm" mean? GPT-2 uses pre-norm (LayerNorm before attention), which is different from the original Transformer paper.
- Chapter 5 will cover training — what does the loss curve actually look like when you train from scratch vs fine-tune?

## Connected files in Bolt
- `llm/neural_model.py` — the FeedForward block is essentially this, just embedded inside GPT
- `llm/neural_model.pth` — saved weights, analogous to what a trained GPT checkpoint looks like
- `modules/Think_Learn_Decide.py` — calls Claude (which runs this architecture) to make clip decisions
- `modules/AI_Title_Generator.py` — calls Claude to generate titles, fires the full transformer on each call
- `modules/Bolt_Memory.py` — loads context for Claude; understanding transformer attention explains why memory structure matters
- `llm/LLMs-from-scratch/ch04/` — the actual notebook for this chapter
