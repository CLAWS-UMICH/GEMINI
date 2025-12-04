"""
Feedforward Neural Network Classifier for Command Classification

A simple 3-layer MLP that takes sentence embeddings as input and
outputs class probabilities for astronaut command intents.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Optional, Tuple


class CommandClassifier(nn.Module):
    """
    Simple feedforward neural network for command classification.
    
    Architecture:
        Input (384) → Hidden (128) → Hidden (64) → Output (num_classes)
        
    Each hidden layer uses:
        - Linear transformation
        - Batch normalization
        - ReLU activation
        - Dropout for regularization
    """
    
    def __init__(
        self,
        embedding_dim: int = 384,
        hidden_dims: List[int] = [128, 64],
        num_classes: int = 8,
        dropout: float = 0.3
    ):
        """
        Initialize the classifier.
        
        Args:
            embedding_dim: Dimension of input embeddings (384 for MiniLM)
            hidden_dims: List of hidden layer dimensions
            num_classes: Number of output classes (intents)
            dropout: Dropout probability for regularization
        """
        super().__init__()
        
        self.embedding_dim = embedding_dim
        self.hidden_dims = hidden_dims
        self.num_classes = num_classes
        self.dropout_rate = dropout
        
        # Build the network layers
        layers = []
        prev_dim = embedding_dim
        
        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim),
                nn.ReLU(),
                nn.Dropout(dropout)
            ])
            prev_dim = hidden_dim
        
        # Output layer (no activation - will use CrossEntropyLoss which includes softmax)
        layers.append(nn.Linear(prev_dim, num_classes))
        
        self.network = nn.Sequential(*layers)
        
        # Initialize weights
        self._init_weights()
    
    def _init_weights(self):
        """Initialize weights using Xavier initialization."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through the network.
        
        Args:
            x: Input tensor of shape (batch_size, embedding_dim)
            
        Returns:
            Logits tensor of shape (batch_size, num_classes)
        """
        return self.network(x)
    
    def predict(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Get predictions with confidence scores.
        
        Args:
            x: Input tensor of shape (batch_size, embedding_dim)
            
        Returns:
            Tuple of:
            - predicted_classes: Tensor of shape (batch_size,)
            - confidences: Tensor of shape (batch_size,) with probability scores
        """
        self.eval()
        with torch.no_grad():
            logits = self.forward(x)
            probabilities = F.softmax(logits, dim=-1)
            confidences, predicted_classes = torch.max(probabilities, dim=-1)
        return predicted_classes, confidences
    
    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        """
        Get probability distribution over all classes.
        
        Args:
            x: Input tensor of shape (batch_size, embedding_dim)
            
        Returns:
            Probabilities tensor of shape (batch_size, num_classes)
        """
        self.eval()
        with torch.no_grad():
            logits = self.forward(x)
            return F.softmax(logits, dim=-1)
    
    def count_parameters(self) -> int:
        """Count the number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
    
    def get_architecture_summary(self) -> str:
        """Get a string summary of the architecture."""
        summary_lines = [
            "CommandClassifier Architecture:",
            f"  Input dimension: {self.embedding_dim}",
            f"  Hidden layers: {self.hidden_dims}",
            f"  Output classes: {self.num_classes}",
            f"  Dropout rate: {self.dropout_rate}",
            f"  Total parameters: {self.count_parameters():,}"
        ]
        return "\n".join(summary_lines)


def create_model(
    num_classes: int = 8,
    embedding_dim: int = 384,
    hidden_dims: Optional[List[int]] = None,
    dropout: float = 0.3
) -> CommandClassifier:
    """
    Factory function to create a CommandClassifier with common configurations.
    
    Args:
        num_classes: Number of intent classes
        embedding_dim: Dimension of input embeddings
        hidden_dims: Hidden layer dimensions (default: [128, 64])
        dropout: Dropout probability
        
    Returns:
        Configured CommandClassifier instance
    """
    if hidden_dims is None:
        hidden_dims = [128, 64]
    
    return CommandClassifier(
        embedding_dim=embedding_dim,
        hidden_dims=hidden_dims,
        num_classes=num_classes,
        dropout=dropout
    )

