"""
Clean PyTorch Neural Network Implementation
Self-taught learning journey: building a classifier from scratch

What this does:
- Creates a neural network with 2 inputs, hidden layers of 30 and 20 neurons, and 2 outputs
- Trains on 5 labeled examples (binary classification on 2D points)
- Achieves 100% accuracy on both training and test data
- Saves the trained model for later use
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import SGD
from torch.utils.data import Dataset, DataLoader


# ============================================================================
# 1. DEFINE THE NEURAL NETWORK CLASS
# ============================================================================

class NeuralNetwork(nn.Module):
    """
    A simple feedforward neural network.

    Architecture:
    - Input layer: 2 features (x, y coordinates)
    - Hidden layer 1: 30 neurons with ReLU activation
    - Hidden layer 2: 20 neurons with ReLU activation
    - Output layer: 2 neurons (logits for binary classification)

    Why ReLU? It introduces non-linearity so the network can learn curves, not just lines.
    Why 2 outputs? One for each class. We use cross-entropy loss to convert logits → probabilities.
    """

    def __init__(self, num_inputs, num_outputs):
        super().__init__()
        # Sequential stacks layers: input → layer1 → ReLU → layer2 → ReLU → output
        self.layers = nn.Sequential(
            nn.Linear(num_inputs, 30),      # 2 inputs → 30 neurons
            nn.ReLU(),                       # Add non-linearity
            nn.Linear(30, 20),               # 30 neurons → 20 neurons
            nn.ReLU(),                       # Add non-linearity again
            nn.Linear(20, num_outputs),      # 20 neurons → 2 outputs
        )

    def forward(self, x):
        """
        Forward pass: push data through all layers.

        Args:
            x: Input tensor of shape (batch_size, 2)

        Returns:
            logits: Raw output scores from the network

        Why raw logits? Cross-entropy loss expects logits, not probabilities.
        It handles the softmax conversion internally for numerical stability.
        """
        logits = self.layers(x)
        return logits


# ============================================================================
# 2. DEFINE THE CUSTOM DATASET CLASS
# ============================================================================

class ToyDataset(Dataset):
    """
    A wrapper around our training data.

    PyTorch's DataLoader expects a Dataset object that implements:
    - __len__: how many samples do we have?
    - __getitem__: give me sample #index

    This allows DataLoader to automatically batch samples for training.
    """

    def __init__(self, X, y):
        """
        Args:
            X: Tensor of shape (num_samples, num_features) — the input points
            y: Tensor of shape (num_samples,) — the labels (0 or 1)
        """
        self.features = X
        self.labels = y

    def __getitem__(self, index):
        """Get a single (feature, label) pair at the given index."""
        one_x = self.features[index]
        one_y = self.labels[index]
        return one_x, one_y

    def __len__(self):
        """Total number of samples."""
        return self.labels.shape[0]


# ============================================================================
# 3. DEFINE THE ACCURACY COMPUTATION FUNCTION
# ============================================================================

def compute_accuracy(model, dataloader):
    """
    Evaluate the model on a dataset and return accuracy.

    Args:
        model: The neural network
        dataloader: A DataLoader (train_loader or test_loader)

    Returns:
        accuracy: Float between 0 and 1 (e.g., 1.0 = 100% correct)

    Why model.eval()? Disables dropout/batch normalization so evaluation is consistent.
    Why torch.no_grad()? Disables gradient tracking (we don't backprop during evaluation).
    """
    model.eval()                              # Put model in evaluation mode
    correct = 0.0
    total_examples = 0

    for idx, (features, labels) in enumerate(dataloader):
        with torch.no_grad():                 # Don't track gradients
            logits = model(features)          # Forward pass

        predictions = torch.argmax(logits, dim=1)  # Pick the class with highest logit
        compare = labels == predictions             # Compare to ground truth
        correct += torch.sum(compare)               # Count correct predictions
        total_examples += len(compare)              # Count total predictions

    return (correct / total_examples).item()


# ============================================================================
# 4. MAIN EXECUTION: DATA, TRAINING, EVALUATION
# ============================================================================

if __name__ == "__main__":

    # --- CREATE TRAINING DATA ---
    # Two classes, 2D points. Class 0 clusters around (-1, 3), class 1 around (2, -1)
    X_train = torch.tensor([
        [-1.2, 3.1],   # class 0
        [-0.9, 2.9],   # class 0
        [-0.5, 2.6],   # class 0
        [2.3, -1.1],   # class 1
        [2.7, -1.5],   # class 1
    ])
    y_train = torch.tensor([0, 0, 0, 1, 1])

    # --- CREATE TEST DATA ---
    X_test = torch.tensor([
        [-0.8, 2.8],   # looks like class 0
        [2.6, -1.6],   # looks like class 1
    ])
    y_test = torch.tensor([0, 1])


    # --- CREATE DATALOADERS ---
    # DataLoader handles batching. batch_size=2 means:
    # - Each gradient step processes 2 samples
    # - With 5 training samples, each epoch has 3 batches (2+2+1)
    train_dataset = ToyDataset(X_train, y_train)
    test_dataset = ToyDataset(X_test, y_test)

    train_loader = DataLoader(train_dataset, batch_size=2, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=2, shuffle=False)


    # --- INITIALIZE MODEL AND OPTIMIZER ---
    torch.manual_seed(123)  # For reproducibility
    model = NeuralNetwork(num_inputs=2, num_outputs=2)
    optimizer = SGD(model.parameters(), lr=0.5)

    # Why SGD with lr=0.5?
    # - SGD = Stochastic Gradient Descent: on each batch, move weights opposite to gradients
    # - lr=0.5 = how big are the steps? Bigger steps = faster learning but might overshoot
    # - For this tiny dataset, 0.5 works well. For real data, you'd tune this.


    # --- TRAINING LOOP ---
    num_epochs = 3

    print("Starting training...")
    print("-" * 70)

    for epoch in range(num_epochs):
        model.train()  # Put model in training mode (enables gradient tracking)

        for batch_idx, (features, labels) in enumerate(train_loader):
            # Forward pass: push batch through network
            logits = model(features)

            # Compute loss: cross-entropy between predictions and ground truth
            # Lower loss = better predictions
            loss = F.cross_entropy(logits, labels)

            # Backward pass: compute gradients
            optimizer.zero_grad()  # Clear old gradients (important!)
            loss.backward()        # Compute new gradients via backprop

            # Update weights: move in the direction that reduces loss
            optimizer.step()

        print(f"Epoch {epoch+1}/{num_epochs} completed | Final batch loss: {loss:.4f}")

    print("-" * 70)
    print("Training finished!\n")


    # --- EVALUATION ---
    print("Evaluating on training data...")
    train_accuracy = compute_accuracy(model, train_loader)
    print(f"Train accuracy: {train_accuracy:.4f} ({train_accuracy*100:.1f}%)")

    print("Evaluating on test data...")
    test_accuracy = compute_accuracy(model, test_loader)
    print(f"Test accuracy: {test_accuracy:.4f} ({test_accuracy*100:.1f}%)")

    # Interpretation: 1.0 = 100% = perfect! All 5 training samples correct, both test samples correct.


    # --- SAVE AND RELOAD THE MODEL ---
    # This shows that the trained weights persist and work later
    print("\n" + "-" * 70)
    print("Saving model to disk...")
    torch.save(model.state_dict(), "neural_model.pth")
    print("Saved as 'neural_model.pth'")

    print("Creating a fresh model and loading the saved weights...")
    fresh_model = NeuralNetwork(num_inputs=2, num_outputs=2)
    fresh_model.load_state_dict(torch.load("neural_model.pth", weights_only=True))
    print("Weights loaded successfully!\n")

    # Verify the fresh model has the same accuracy
    print("Verifying fresh model accuracy...")
    reloaded_accuracy = compute_accuracy(fresh_model, test_loader)
    print(f"Reloaded model test accuracy: {reloaded_accuracy:.4f}")

    if reloaded_accuracy == test_accuracy:
        print("✓ Reloaded model performs identically to the original!")

    print("-" * 70)
