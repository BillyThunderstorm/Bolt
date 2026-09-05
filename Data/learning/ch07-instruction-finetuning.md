# Ch07 — Finetuning to Follow Instructions
*Captured: 2026-08-28 | Source: LLMs from Scratch, Chapter 7*

## The core idea

Chapter 5's pretrained model can continue text. It cannot reliably do what you *asked*. "Below is an instruction... ### Instruction: ... ### Response:" is just more tokens to a base model — it will ramble in that style instead of answering.

Instruction finetuning (supervised finetuning, SFT) teaches the same next-token loss, but only on examples that look like: instruction (+ optional input) → the answer you want. After a couple of epochs the model learns the template and starts filling in `### Response:` with an actual answer. That is the difference between a base checkpoint and the chat models Bolt calls through `LLM_Handler` (Grok, OpenAI, instruction-tuned Ollama tags).

Unlike ch06, you do **not** replace the vocab-sized output head. You keep generating tokens. The specialization is in the *data format* and in masking the loss so padding does not get trained as if it were language.

## What it builds

1. **Dataset.** ~1,100 Alpaca-style JSON records: `instruction`, `input` (often empty), `output`. Split 85/10/5 train/test/val (935 / 110 / 55 in the standalone script).
2. **Prompt template** (`format_input`):

```
Below is an instruction that describes a task. Write a response that appropriately completes the request.

### Instruction:
{instruction}

### Input:
{input}          # omitted when input is empty

### Response:
{output}         # only present during training
```

3. **`InstructionDataset`.** Pre-tokenizes `format_input(entry) + "\n\n### Response:\n" + output`.
4. **`custom_collate_fn`.** This is the new engineering:
   - Pad *per batch* to that batch's max length (not one global width like ch06) — less wasted compute.
   - Append `<|endoftext|>` (50256) as a real end-of-example token, then pad with more 50256.
   - Targets are inputs shifted by 1 (standard next-token).
   - **Mask padding in the loss:** keep the first EOS in targets; set later pad IDs to `ignore_index = -100` so `cross_entropy` skips them. Otherwise the model spends its budget predicting padding.
   - Optional `allowed_max_length=1024` to stay inside GPT-2 context.
   - Optional extra trick (mentioned, not required in the main script): also mask the instruction tokens so loss is only on the response.
5. **Load GPT-2 medium (355M), not small.** Instruction following needs more capacity than spam/ham. Full model is trainable this time (no frozen backbone). AdamW `5e-5`, 2 epochs. Loss drops fast in epoch 1 (e.g. ~3.8 → ~0.9).
6. **Generate.** Same `generate()` as ch05, with `eos_id=50256` and up to 256 new tokens. Strip the prompt and the `### Response:` header to store `model_response`.
7. **Evaluate with a bigger LLM.** `ollama_evaluate.py` asks local Llama 3 (`http://localhost:11434/api/chat`, temperature 0) to score each response 0–100 vs the gold `output`. Standalone run: average ~51.75/100 — a baseline, not a trophy. Human/GPT-4 eval lives in `ch07/03_model-evaluation`.

Bonus: DPO preference tuning (`ch07/04_preference-tuning-with-dpo`), synthetic data generation, dataset utilities, a UI. DPO is the "chosen vs rejected answer" stage after SFT — how base+SFT models get aligned to "this reply is better than that one."

## Key vocab

| Term | Plain meaning |
|------|---------------|
| SFT / instruction finetuning | Train on instruction→answer pairs so the model fills in the response, not random continuation |
| Alpaca template | The `### Instruction / Input / Response` wrapper this chapter uses |
| Collate function | How a `DataLoader` stacks examples of different lengths into one batch |
| `ignore_index` (-100) | Sentinel that `cross_entropy` skips; used so padding is not a training target |
| EOS / `<\|endoftext\|>` | Token that means "stop." Training: end of example. Inference: stop generating |
| LLM-as-judge | Use a stronger model (Llama 3 via Ollama) to score another model's answers |
| DPO | Direct Preference Optimization — finetune on preferred vs rejected replies without a separate reward model |
| LoRA (appendix E) | Train a few small adapter matrices instead of all 355M weights |

## Architecture / code pieces

Ch07 reuses ch05's `GPTModel`, `train_model_simple`, `generate`, and weight loader. New code is almost all data + eval:

| Piece | Where | Job |
|-------|-------|-----|
| `format_input` | `gpt_instruction_finetuning.py` | Alpaca prompt |
| `InstructionDataset` | same | Tokenize full instruction+response |
| `custom_collate_fn` | same | Batch pad, shift targets, -100 mask |
| `train_model_simple` | `previous_chapters.py` | Same next-token loop as pretraining |
| `generate` + `eos_id` | same | Stop at EOS when answering |
| `ollama_evaluate.py` | same folder | Llama 3 scores on localhost:11434 |
| DPO bonus | `ch07/04_preference-tuning-with-dpo/` | Preference alignment after SFT |

## How this connects to chapters 5 and 6

- **Vs ch05:** same loss, same architecture, same generate(). Different data: unlabeled stream vs structured instruction/response. Pretraining teaches English; SFT teaches "do the task, then stop."
- **Vs ch06:** ch06 *replaces* the head and predicts one of N labels from the last token. Ch07 *keeps* the vocab head and predicts a whole answer. Ch06 is the specialist; ch07 is the generalist Bolt already talks to.
- Frozen vs full: classification froze most of GPT-2. Instruction SFT trains the whole 355M so it can change how it writes, not just a 2-logit head.

## Why this matters for Bolt

Every chatty thing Bolt does is instruction following, not classification and not raw pretraining:

- `LLM_Handler.ask_llm` is talking to models that already had this stage (and usually RLHF/DPO after it). Prompts work because SFT taught the template "user asks → assistant answers."
- Local Ollama models on `localhost:11434` are the same eval path as `ollama_evaluate.py`. Bolt's `BOLT_LLM_MODE=local` is only as good as whichever instruct-tuned weights Ollama loaded (`llama3`, etc.), not a base GPT-2.
- Prompt structure in `Bolt_Chat.py` / memory context is a lightweight stand-in for SFT. If a local model ignores instructions, the next real fix is SFT (or picking a better instruct checkpoint), not a longer system prompt.
- Padding/`-100` is the production detail behind "why did my finetune learn to emit blank lines?" If we ever SFT a Bolt style model on titles, briefs, or clip descriptions, mask pads and ideally mask the instruction so the model is graded only on the answer.
- LLM-as-judge is a pattern Bolt can reuse: score titles, briefing quality, or clip copy with a local Llama instead of paying Grok for every rubric pass. Keep temperature 0 for judges.
- DPO is the later step if we want "this title style, not that one" without writing a reward model.

## What I can do with this now

- Tell a base checkpoint from an instruct checkpoint, and always pull the instruct one for Bolt chat.
- Format any future Bolt training JSON as `{instruction, input, output}` and reuse `format_input`.
- Evaluate a local model the way the book does: generate on a test split, score with Ollama, track the average.
- Decide ch06 vs ch07 per feature: labels → classifier head; "write/do X" → instruct model / SFT.
- Read appendix E (LoRA) before ever full-finetuning 355M on a laptop.

## Questions still open

- Mask instruction tokens in the loss, or train on the full prompt? Book notes both; response-only is the usual production choice.
- For Bolt, is a LoRA on a local instruct model enough to learn Billy's voice, or do we stay with prompting + memory?
- DPO dataset: where would preferred/rejected pairs come from (posted vs unposted titles, kept vs killed clips)?

## Connected files in Bolt
- `3rd_Party/llm/LLMs-from-scratch/ch07/01_main-chapter-code/` — `ch07.ipynb`, `gpt_instruction_finetuning.py`, `ollama_evaluate.py`
- `3rd_Party/llm/LLMs-from-scratch/ch07/04_preference-tuning-with-dpo/` — DPO bonus
- `3rd_Party/llm/LLMs-from-scratch/appendix-E/` — LoRA (parameter-efficient alternative)
- `Data/learning/ch05-pretraining.md` — base next-token training this chapter specializes
- `Data/learning/ch06-finetuning-classification.md` — the other finetune fork (labels, not answers)
- `Core/modules/LLM_Handler.py` — calls instruct-tuned OpenAI / xAI / Ollama (`http://localhost:11434/v1`)
- `Core/modules/LLM_Budget.py` — local instruct models vs paid API
- `Core/modules/Bolt_Chat.py` — personality via prompting, which SFT is the trained form of
- `Core/modules/Bolt_Memory.py` — extra instruction/context tokens at inference
- `Data/content/ai-development.md` — learning lane / content angles
