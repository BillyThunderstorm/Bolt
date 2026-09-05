# Ch06 — Finetuning for Text Classification
*Captured: 2026-08-28 | Source: LLMs from Scratch, Chapter 6*

## The core idea

Pretraining (ch05) makes a general next-token predictor. Classification finetuning turns that predictor into a specialist with a small, fixed set of labels — here, spam vs ham. The model is no longer asked to write the next word. It is asked: "given this whole text, which class is it?"

This is the cheaper, narrower cousin of instruction finetuning (ch07). A classifier can only emit classes it saw in training. That limitation is a feature: if Bolt needs "keep / kill this clip," "spam comment," or "this title is clickbait," a two-class head is easier to train, cheaper to run, and easier to evaluate (accuracy %) than a general chat model.

## What it builds

Start from pretrained GPT-2 small (124M) via the ch05 weight loader. Then:

1. **Data.** UCI SMS Spam Collection. Heavily imbalanced (way more ham), so they undersample ham to match the spam count, map `ham→0`, `spam→1`, and split 70/10/20 train/val/test.
2. **`SpamDataset`.** Tokenize with GPT-2 BPE. Pad every example to the longest training SMS using `<|endoftext|>` (id 50256). Truncate if needed. Val/test use the *training* max length so batches line up.
3. **Replace the output head.** Freeze almost the whole model (`requires_grad = False`). Swap `out_head` from `Linear(emb_dim → 50257)` to `Linear(emb_dim → 2)`. Then unfreeze the **last TransformerBlock** and **final LayerNorm** — training only the last layer works, but unfreezing the last block noticeably helps.
4. **Read the last token.** GPT still emits a vector per input token, but classification uses `logits[:, -1, :]` only. Because padding is `<|endoftext|>` on the right, the last position is the model's "I've seen the whole padded message" slot. Predict class from that.
5. **Train.** Same loop as ch05, but loss is cross-entropy over **2 classes**, not 50,257 tokens. Track accuracy, not just loss. AdamW at a much smaller lr (`5e-5`). ~5 epochs. On an M3 Air this is minutes, not hours.
6. **Use it.** Encode a new SMS, take the last-token logits, `argmax` → ham or spam. Save `state_dict` so you do not retrain.

Bonus material: last-token vs first-token experiments, longer context, IMDb sentiment vs other models, a tiny UI.

## Key ideas in plain language

- **Finetuning vs training from scratch.** You keep the pretrained features (English, attention over a message) and only adapt the top of the network to a new output space. That is why a few hundred labeled SMS messages are enough.
- **Frozen backbone + small trainable set.** Most of GPT-2 is a feature extractor. Gradients only flow through the new 2-class head, the last block, and final LayerNorm. Faster, less likely to wreck the pretrained knowledge (catastrophic forgetting).
- **Last-token pooling.** No special CLS token like BERT. Causal GPT already crams left-to-right context into the rightmost token, so that is the classification summary.
- **Pad, don't truncate-to-shortest.** Truncating would delete the actual message. Padding with EOS is the ch02 trick reused as a batching tool.
- **Accuracy is the metric that matters now.** Loss still drives training, but "was the label right?" is what you ship. Train and val accuracy staying together means you are not just memorizing SMS phrasing.

## Architecture / code pieces

```
pretrained GPT-2 (frozen except last block + final LayerNorm)
    ↓
token embeddings + 12 transformer blocks
    ↓
final LayerNorm
    ↓
NEW out_head: 768 → 2   (was 768 → 50257)
    ↓
use logits at the last position only
    ↓
cross-entropy vs {0, 1}
```

| Piece | Where | Job |
|-------|-------|-----|
| `SpamDataset` | `gpt_class_finetune.py` | Tokenize, pad, label |
| `create_balanced_dataset` / `random_split` | same | Fix class skew, 70/10/20 |
| `model.out_head = Linear(emb, 2)` | same | Classification head |
| `calc_loss_batch` uses `[:, -1, :]` | same | Last-token class loss |
| `calc_accuracy_loader` | same | Percent correct |
| `train_classifier_simple` | same | Finetune loop + acc logging |
| `load-finetuned-model.ipynb` | same folder | Reload later |

## How this connects to chapter 5

Ch05 trained *every* weight to predict the next token and loaded GPT-2 as a language model. Ch06 **reuses those weights**, changes the question from "what token comes next?" to "which of these N labels?", and only lets a few layers keep learning. Decoding knobs (temperature, top-k) mostly go away — you want `argmax` over two classes, not creative sampling.

Ch05's `neural_model.py` lesson is the baby version of this: labeled data → `Dataset` → `DataLoader` → cross-entropy → accuracy. Ch06 is that loop attached to a 124M pretrained backbone.

## Why this matters for Bolt

Bolt already ranks and gates content with numeric scores (`Clip_Ranker`) and a local decision layer (`Think_Learn_Decide`) that is deliberately *not* a cloud LLM. Chapter 6 is the blueprint for replacing brittle heuristics with a small finetuned head:

- Clip keep/kill, hook vs no-hook, "this comment is spam," "this title matches the brand" are classification problems, not chat problems. Do not spend Grok API budget (`LLM_Budget` high-value vs low-value tasks) on a 2-class decision.
- Freeze almost everything, train the last block + a tiny head, run on CPU/MPS. That matches Bolt's local-first rule.
- Use the last-token trick if the backbone is a causal LM (GPT/Ollama-style). If you ever wrap a local model for clip labels, the dataset object should look like `SpamDataset`: tokenize, pad, integer labels.
- Balance the classes. Clip datasets will be as skewed as SMS ham/spam ("most clips are meh"). Undersample or you will get a model that always says ham/meh and looks accurate.
- Evaluate with accuracy on a held-out set, then save weights. Same discipline as `clip_history.json`, but with an actual model file.

## What I can do with this now

- Sketch a Bolt `SpamDataset`-style class for any labeled CSV (clips, titles, comments).
- Know when to use a classifier instead of `ask_llm`: fixed labels, cheap, local, measurable.
- Read `gpt_class_finetune.py` as the template for "load GPT-2 → swap head → train last block."
- Treat `Clip_Ranker`'s score as the thing a future classification head could predict directly (keep/review/kill tiers).

## Questions still open

- Last token vs mean-pool vs a dedicated CLS — bonus experiments exist; for short clip titles last-token is probably enough.
- LoRA (appendix E) would let Bolt adapt a local Ollama model without storing a full 124M copy per task.
- How many labeled Bolt examples before this beats the current heuristic ranker?

## Connected files in Bolt
- `3rd_Party/llm/LLMs-from-scratch/ch06/01_main-chapter-code/` — `ch06.ipynb`, `gpt_class_finetune.py`
- `Data/learning/ch05-pretraining.md` — the pretrained weights this chapter starts from
- `Data/learning/ch05-neural-network-basics.md` — toy labeled-data loop
- `Core/modules/Clip_Ranker.py` — heuristic scoring that a classifier head could replace or sit under
- `Core/modules/Think_Learn_Decide.py` — local, no-cloud decisions; same niche as a small classifier
- `Core/modules/LLM_Budget.py` — classification is how you keep low-value tasks off the paid API
- `Core/modules/LLM_Handler.py` — still used when the task is generation, not labels
