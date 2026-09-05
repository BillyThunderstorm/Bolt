# Ch05 — Pretraining on Unlabeled Data
*Captured: 2026-08-28 | Source: LLMs from Scratch, Chapter 5*

> Note: `ch05-neural-network-basics.md` is a separate toy PyTorch lesson from `neural_model.py`. This file is the actual book chapter 5.

## The core idea

Chapter 4 left you with a real GPT architecture that still produced garbage, because the weights were random. Chapter 5 is how you teach it: pretraining. You never hand the model "the meaning of English." You give it raw text, slide a window over it, and train it to predict the next token. Do that enough times and language, style, and a surprising amount of world knowledge fall out of that one task.

The training target is simple. For every input sequence, the target is the same sequence shifted one token to the right. The model outputs a logit for every vocabulary item at every position. Cross-entropy loss then punishes it for putting low probability on the true next token. Minimize that number and the model gets better at generating text.

Two different "pretrained" things show up here, and Bolt needs both:

1. **Train from scratch** on a tiny story (`the-verdict.txt`, ~5,145 tokens) so the loop is visible: loss goes down, generated text goes from noise to something that vaguely matches the training style.
2. **Load OpenAI GPT-2 weights** (124M / 355M / 774M / 1558M) into the same `GPTModel` class. That is how you skip months of pretraining and start from a model that already speaks English.

## How the loss actually works

1. Tokens in → model → logits of shape `(batch, seq_len, vocab_size)`.
2. Flatten batch and sequence so PyTorch `cross_entropy` sees `(batch*seq_len, vocab_size)` vs target IDs.
3. Cross-entropy = negative log-likelihood of the correct next token. Lower is better. Zero would mean the model is certain and always right.
4. **Perplexity** = `exp(cross_entropy)`. Plain-language reading: "how many vocabulary items is the model still confused between?" Loss 10.8 → perplexity ~48k, basically "could be any GPT-2 token." Loss 3 → perplexity ~20, a much narrower guess.

The training loop (`train_model_simple` in `gpt_train.py`) is the same loop as the toy classifier, just on tokens:

- `optimizer.zero_grad()` → `loss.backward()` → `optimizer.step()`
- Optimizer is **AdamW** (lr `5e-4`, weight decay `0.1`), not SGD
- Every N steps, switch to `model.eval()`, compute train + val loss with `torch.no_grad()`, then go back to train
- After each epoch, generate a sample from `"Every effort moves you"` so you can *see* the model getting less drunk
- Track tokens seen, not just epochs — that is the real unit of pretraining progress

Educational config: GPT-2 124M shape, but context shortened to 256, batch size 2, 10 epochs, 90/10 train/val split, stride = context length. This overfits a short story on purpose. Real pretraining uses huge corpora (bonus folder: Project Gutenberg).

## Decoding: greedy vs temperature vs top-k

Untrained and even trained models that always pick `argmax` (greedy) sound repetitive. Chapter 5 adds the knobs Bolt already exposes in API calls:

- **Temperature**: divide logits by T before softmax. T < 1 sharpens (more confident, more boring). T > 1 flattens (more random, more likely to go off the rails). T → 0 is greedy.
- **Top-k**: zero out everything except the k most likely tokens, then sample. Lets you raise temperature without sampling from the garbage tail of the vocabulary.
- Combined `generate()` in `gpt_generate.py` also supports an EOS id so generation can stop early.

This is the missing math from the chapter 4 open questions: temperature is just `softmax(logits / T)`.

## Saving weights, then stealing GPT-2's

`torch.save(model.state_dict(), "model.pth")` / `load_state_dict` is the checkpoint format. You save weights, not the Python class.

Then the chapter maps OpenAI's TensorFlow GPT-2 checkpoint into the from-scratch model: split the fused QKV matrix, transpose some weights, copy LayerNorm scale/shift, and **tie** the output head to the token embedding (`wte`). If even one tensor is assigned wrong, the model emits nonsense — coherent English is the smoke test that loading worked.

`qkv_bias=True` when loading GPT-2; the from-scratch educational config used `False`. Dropout is 0.0 at inference.

## Architecture / code pieces

| Piece | Where | Job |
|-------|-------|-----|
| `GPTModel` + dataloader | `previous_chapters.py` (ch04 + ch02) | The network and the sliding-window dataset |
| `calc_loss_batch` / `calc_loss_loader` | `gpt_train.py` | Cross-entropy over next tokens |
| `train_model_simple` | `gpt_train.py` | The pretraining loop |
| `generate` + temperature/top-k | `gpt_generate.py` | Sampling text |
| `download_and_load_gpt2` / `load_weights_into_gpt` | `gpt_generate.py`, `gpt_download.py` | Import OpenAI weights |
| Bonus | `ch05/03_bonus_pretraining_on_gutenberg`, `04_learning_rate_schedulers`, appendix D | Bigger data, warmup, cosine decay, grad clip |

## How this connects to chapter 4

Ch04 built LayerNorm, GELU, FeedForward, residual TransformerBlocks, and greedy `generate_text_simple`. Ch05 keeps that class unchanged and adds: a loss, an optimizer loop, better decoding, checkpoints, and a way to load a model that was pretrained at OpenAI scale. The untrained `"Hello, I am Featureiman..."` output is now a before-picture.

## Why this matters for Bolt

Bolt is mostly an *inference* user of pretrained models (Ollama locally, Grok/OpenAI when the budget says so). This chapter is why that split exists:

- Pretraining is the expensive stage. Bolt should not train a 124M model from scratch for titles or chat. Load a pretrained checkpoint (Ollama) or call a pretrained API.
- `LLM_Budget.py` `local` / `light` / `full` is an operational version of this fact: next-token generation is cheap; producing those weights was not.
- Temperature and top-k are not magic API spices. They are the exact decoding controls from `generate()`. Title generation should stay low-T / greedy-ish. Brainstorming can go higher T with a top-k cap.
- Train vs val loss is the same "is it memorizing?" check you want before trusting any local classifier or ranker. If train loss crashes and val loss rises, the model parroted the set.
- `state_dict` save/load is the pattern behind `Clip_Ranker` history, any future local head, and Ollama model files: weights are data, the architecture is code.

## What I can do with this now

- Read `3rd_Party/llm/LLMs-from-scratch/ch05/01_main-chapter-code/gpt_train.py` and recognize every line of the Bolt toy neural-net loop, scaled to tokens.
- Tune decoding in `Core/modules/LLM_Handler.py` with intent: temperature is a sharpness dial, not a "creativity percentage."
- Prefer loading a local pretrained model (Ollama) over training from scratch for any Bolt language task.
- Use perplexity/loss language when a local model sounds drunk: high uncertainty, not "the AI is broken."
- Checkpoint anything you do train (`state_dict`), matching how GPT-2 weights get reloaded into `GPTModel`.

## Questions still open

- How far can a Mac-local Ollama model get on Bolt-specific tasks before you need instruction finetuning (ch07) instead of prompt-only use?
- Appendix D add-ons (warmup, cosine annealing, grad clip) — worth it only if we actually pretrain/finetune locally.
- Weight tying: we load it for GPT-2; would a Bolt-trained head want the same trick?

## Connected files in Bolt
- `3rd_Party/llm/LLMs-from-scratch/ch05/01_main-chapter-code/` — `ch05.ipynb`, `gpt_train.py`, `gpt_generate.py`
- `Data/learning/ch04-gpt-architecture.md` — the untrained model this chapter trains
- `Data/learning/ch05-neural-network-basics.md` — same train loop on a tiny classifier, not the book chapter
- `Core/modules/LLM_Handler.py` — inference against pretrained models; temperature/sampling live here
- `Core/modules/LLM_Budget.py` — why Bolt defaults to local/pretrained instead of training
- `Core/modules/Bolt_Memory.py` — context tokens the pretrained model attends over at inference
- `Data/content/ai-development.md` — learning lane this chapter belongs in
