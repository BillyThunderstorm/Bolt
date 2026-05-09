# Ch01 — What Are LLMs?
*Captured: 2026-05-01 | Source: LLMs from Scratch, Chapter 1*

## The core idea

An LLM (Large Language Model) is a neural network trained to predict the next word in a sequence. That's it. Everything Claude does, everything GPT does — it comes down to "given these words, what word most likely comes next?" Trained on enough text with enough parameters, that simple task produces something that can reason, explain, code, and hold a conversation.

The "large" part matters: scale changes the behavior. Small models memorize. Large models generalize — they develop emergent abilities that weren't explicitly trained in.

## How they're built (the three-stage picture)

1. **Pretraining** — Feed the model billions of words. It learns language patterns, world knowledge, reasoning structure. This is expensive and done once by companies like Anthropic or OpenAI.
2. **Fine-tuning** — Take the pretrained model and train it further on specific tasks (follow instructions, answer questions helpfully, stay safe). This shapes the personality and behavior.
3. **Inference** — You talk to it. The model generates one token at a time, each one conditioned on everything before it.

## Why this matters for Bolt

Bolt uses Claude (Anthropic's LLM) as its brain — for writing titles, answering questions, doing recalls from memory. Understanding that Claude is a next-token predictor explains *why* prompts matter so much: every word in the system prompts in Bolt_Chat.py and Bolt_Memory.py are written carefully. Each prompt shapes what tokens Claude thinks should come next. Better prompts = better outputs.

## What Billy can do with this

- Understand why prompt engineering works (you're steering the probability distribution)
- Know why giving Claude more context = better answers (more tokens to condition on)
- Recognize that Bolt's memory system works *because* of this: loading memory into context makes Claude "remember" by giving it the right conditioning tokens

## Connected files in Bolt
- `modules/Bolt_Memory.py` — loads memory context to condition Claude's responses
- `modules/AI_Title_Generator.py` — prompts Claude to generate titles (next-token prediction at work)
- `modules/Bolt_Chat.py` — system prompt shapes Bolt's personality via token conditioning
