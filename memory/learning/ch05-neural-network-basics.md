# Ch05 - Neural Network Basics
*Captured: 2026-05-29 | Source: Desktop `Neural_Model.py`, cleaned into `llm/neural_model.py`*

## The core idea

A neural network learns by making a prediction, measuring how wrong it was, calculating gradients with backpropagation, and updating its weights with an optimizer.

The cleaned example in `llm/neural_model.py` uses a tiny PyTorch classifier to make the learning loop visible:

1. create labeled toy data
2. wrap it in a `Dataset`
3. batch it with a `DataLoader`
4. define a feedforward `NeuralNetwork`
5. calculate cross-entropy loss
6. call `loss.backward()`
7. update weights with SGD
8. evaluate accuracy
9. save and reload the model weights

## Why this matters for Bolt

This is part of Billy's AI development learning path. Bolt should remember that the goal is not only to use AI APIs, but to understand the building blocks well enough to make smarter decisions about future local models, training experiments, retrieval, and teammate behavior.

## What clicked

- Tensors are the basic data containers.
- Layers transform inputs into outputs.
- ReLU gives the model non-linearity.
- Loss tells the model how wrong it was.
- Backpropagation calculates how each weight contributed to the error.
- The optimizer nudges weights toward lower loss.
- Input dimensions must match the model's first layer.

## Connected files in Bolt

- `llm/neural_model.py` - cleaned runnable PyTorch example
- `memory/content/ai-development.md` - broader AI learning lane
- `memory/content/full-creator-vision.md` - why AI learning belongs in the creator vision
