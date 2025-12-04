# Simple Neural Network for Astronaut Command Classification

A PyTorch-based command classification system using Sentence-BERT embeddings and a feedforward neural network. This prototype is part of the CLAWS AI Subteam's baseline system for mapping astronaut commands to specific functions.

## Architecture Overview

```
[Astronaut Command Text] 
        ↓
[Sentence-BERT Encoder] → 384-dim embedding (all-MiniLM-L6-v2)
        ↓
[Feedforward Neural Network]
    - Input: 384
    - Hidden: 128 (BatchNorm + ReLU + Dropout)
    - Hidden: 64 (BatchNorm + ReLU + Dropout)
    - Output: 8 classes (Softmax)
        ↓
[Predicted Intent + Confidence Score]
```

## Intent Classes

| Intent | Description | Example |
|--------|-------------|---------|
| `navigate` | Moving to or locating items/locations | "Take me to the oxygen tank" |
| `inspect` | Viewing diagnostic or status information | "Show diagnostic info for this panel" |
| `adjust` | Modifying settings or parameters | "Increase temperature by 5 degrees" |
| `query` | Asking questions about system state | "What is the current pressure reading?" |
| `alert` | Flagging or marking issues | "Mark this as critical" |
| `log` | Recording information or events | "Record maintenance completed" |
| `help` | Requesting assistance or instructions | "How do I replace the filter?" |
| `cancel` | Stopping or aborting actions | "Stop current action" |

## Project Structure

```
SimpleNeuralNetwork/
├── data/
│   └── commands.json          # Synthetic dataset (400 examples, 8 intents)
├── models/
│   ├── __init__.py
│   └── classifier.py          # Neural network definition
├── src/
│   ├── __init__.py
│   ├── dataset.py             # Data loading utilities
│   ├── embeddings.py          # Sentence-BERT wrapper with caching
│   ├── train.py               # Training loop with early stopping
│   └── inference.py           # Inference pipeline
├── notebooks/
│   └── evaluation.ipynb       # Analysis and metrics
├── checkpoints/               # Saved models and results
├── requirements.txt
└── README.md
```

## Quick Start

### Installation

```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Training

```bash
python -m src.train
```

This will:
- Load the command dataset
- Compute sentence embeddings
- Train the classifier with early stopping
- Save the best model to `checkpoints/`

### Inference

```python
from src.inference import load_classifier

# Load trained model
classifier = load_classifier()

# Classify a command
result = classifier.classify("Navigate to the airlock")
print(f"Intent: {result['intent']}")
print(f"Confidence: {result['confidence']:.2%}")
print(f"Latency: {result['latency_ms']['total']:.1f}ms")
```

### Interactive Demo

```bash
python -m src.inference
```

### Evaluation

Open `notebooks/evaluation.ipynb` to:
- View accuracy, precision, recall, F1 metrics
- Generate confusion matrices
- Run latency benchmarks

## Model Comparison for Team

### Simple Neural Network + Sentence Embeddings

| Aspect | Assessment | Notes |
|--------|------------|-------|
| **Complexity** | Low | ~58K parameters, easy to understand and modify |
| **Interpretability** | Medium | Can inspect embeddings and layer activations, but hidden layers are opaque |
| **Real-time Performance** | Fast | ~15-30ms total (embedding ~10-25ms, NN inference <1ms) |
| **Training Data Needs** | Moderate | Benefits significantly from pre-trained sentence embeddings |
| **Customization** | Easy | Simple to add layers, adjust dropout, change architecture |
| **Deployment Size** | Medium | ~80MB for sentence model + ~1MB for classifier |

### Pros

1. **Pre-trained Knowledge**: Sentence-BERT provides rich semantic understanding out of the box, reducing the need for large training datasets
2. **Fast Inference**: The feedforward network is extremely fast (<1ms), making total inference time dominated by embedding computation
3. **Simple Architecture**: Easy to understand, debug, and modify
4. **Good Generalization**: Embeddings capture semantic similarity, so the model generalizes well to paraphrased commands
5. **Low Training Time**: Converges quickly (typically <1 minute on CPU)
6. **Deterministic**: Same input always produces same output (unlike some transformer variants)

### Cons

1. **Two-Stage Pipeline**: Requires both embedding model and classifier, adding complexity
2. **Fixed Embedding Model**: Cannot fine-tune the sentence encoder without additional effort
3. **Limited Context Window**: All-MiniLM-L6-v2 has 256 token limit (usually sufficient for commands)
4. **Embedding Model Size**: The 80MB sentence model may be large for some edge deployments
5. **Less Powerful**: May not capture nuances as well as fine-tuned transformers
6. **Hidden Layer Opacity**: Harder to explain why a specific prediction was made

### Comparison with Other Approaches

| Approach | Complexity | Speed | Accuracy Potential | Interpretability |
|----------|------------|-------|-------------------|------------------|
| **Simple NN + Embeddings** | Low | Fast | Good | Medium |
| Small Transformer (DistilBERT) | Medium | Moderate | Excellent | Low |
| Decision Tree (Random Forest) | Low | Fast | Moderate | High |

### Recommendation

The Simple Neural Network with Sentence Embeddings offers the best balance for a baseline system:
- Fast enough for real-time AR applications
- Good accuracy with minimal training data
- Simple to deploy and maintain
- Easy to iterate and improve

For production, consider this as the initial baseline, with potential upgrade to a fine-tuned transformer if accuracy requirements increase.

## Configuration

### Training Parameters

Edit `src/train.py` or pass arguments to `train_model()`:

```python
train_model(
    epochs=50,           # Maximum training epochs
    batch_size=32,       # Training batch size
    learning_rate=0.001, # Adam learning rate
    patience=10,         # Early stopping patience
    hidden_dims=[128, 64], # Hidden layer sizes
    dropout=0.3          # Dropout rate
)
```

### Model Architecture

Edit `models/classifier.py` to modify:
- Hidden layer dimensions
- Activation functions
- Dropout rates
- Batch normalization settings

## API Reference

### CommandClassifierInference

```python
classifier = load_classifier()

# Single command
result = classifier.classify("command text")
# Returns: {"command", "intent", "confidence", "latency_ms"}

# With all probabilities
result = classifier.classify("command text", return_all_probs=True)
# Returns: {"command", "intent", "confidence", "latency_ms", "all_probabilities"}

# Batch classification
results = classifier.classify_batch(["cmd1", "cmd2", "cmd3"])

# Benchmark latency
stats = classifier.benchmark(test_commands, num_runs=100)
```

## Dependencies

- `torch>=2.0.0` - Neural network framework
- `sentence-transformers>=2.2.0` - Pre-trained sentence embeddings
- `scikit-learn>=1.3.0` - Metrics and data splitting
- `numpy>=1.24.0` - Numerical operations
- `pandas>=2.0.0` - Data handling
- `matplotlib>=3.7.0` - Visualization
- `seaborn>=0.12.0` - Enhanced plots
- `tqdm>=4.65.0` - Progress bars

## Team

CLAWS AI Subteam - Model Architecture Team

## License

Internal use for CLAWS project.

