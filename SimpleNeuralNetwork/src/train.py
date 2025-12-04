"""
Training Pipeline for Command Classifier

Implements training loop with:
- Validation monitoring
- Early stopping
- Model checkpointing
- Training metrics logging
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from tqdm import tqdm

import sys
sys.path.append(str(Path(__file__).parent.parent))

from models.classifier import CommandClassifier, create_model
from src.dataset import DataProcessor, CommandDataset


class EarlyStopping:
    """
    Early stopping to stop training when validation loss stops improving.
    """
    
    def __init__(self, patience: int = 5, min_delta: float = 0.001):
        """
        Args:
            patience: Number of epochs to wait before stopping
            min_delta: Minimum change to qualify as improvement
        """
        self.patience = patience
        self.min_delta = min_delta
        self.counter = 0
        self.best_loss = None
        self.should_stop = False
    
    def __call__(self, val_loss: float) -> bool:
        """
        Check if training should stop.
        
        Args:
            val_loss: Current validation loss
            
        Returns:
            True if training should stop
        """
        if self.best_loss is None:
            self.best_loss = val_loss
        elif val_loss > self.best_loss - self.min_delta:
            self.counter += 1
            if self.counter >= self.patience:
                self.should_stop = True
        else:
            self.best_loss = val_loss
            self.counter = 0
        
        return self.should_stop


class Trainer:
    """
    Handles the complete training process for the command classifier.
    """
    
    def __init__(
        self,
        model: CommandClassifier,
        train_loader: DataLoader,
        val_loader: DataLoader,
        device: Optional[str] = None,
        checkpoint_dir: Optional[str] = None
    ):
        """
        Initialize the trainer.
        
        Args:
            model: CommandClassifier model to train
            train_loader: DataLoader for training data
            val_loader: DataLoader for validation data
            device: Device to train on ('cpu', 'cuda', or None for auto)
            checkpoint_dir: Directory to save checkpoints
        """
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)
        
        self.model = model.to(self.device)
        self.train_loader = train_loader
        self.val_loader = val_loader
        
        if checkpoint_dir is None:
            checkpoint_dir = Path(__file__).parent.parent / "checkpoints"
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        # Training history
        self.history: Dict[str, List[float]] = {
            "train_loss": [],
            "val_loss": [],
            "train_acc": [],
            "val_acc": []
        }
    
    def train_epoch(
        self,
        optimizer: optim.Optimizer,
        criterion: nn.Module
    ) -> Tuple[float, float]:
        """
        Train for one epoch.
        
        Returns:
            Tuple of (average_loss, accuracy)
        """
        self.model.train()
        total_loss = 0.0
        correct = 0
        total = 0
        
        for embeddings, labels in self.train_loader:
            embeddings = embeddings.to(self.device)
            labels = labels.to(self.device)
            
            optimizer.zero_grad()
            outputs = self.model(embeddings)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item() * embeddings.size(0)
            _, predicted = torch.max(outputs, 1)
            correct += (predicted == labels).sum().item()
            total += labels.size(0)
        
        avg_loss = total_loss / total
        accuracy = correct / total
        return avg_loss, accuracy
    
    @torch.no_grad()
    def validate(self, criterion: nn.Module) -> Tuple[float, float]:
        """
        Validate the model.
        
        Returns:
            Tuple of (average_loss, accuracy)
        """
        self.model.eval()
        total_loss = 0.0
        correct = 0
        total = 0
        
        for embeddings, labels in self.val_loader:
            embeddings = embeddings.to(self.device)
            labels = labels.to(self.device)
            
            outputs = self.model(embeddings)
            loss = criterion(outputs, labels)
            
            total_loss += loss.item() * embeddings.size(0)
            _, predicted = torch.max(outputs, 1)
            correct += (predicted == labels).sum().item()
            total += labels.size(0)
        
        avg_loss = total_loss / total
        accuracy = correct / total
        return avg_loss, accuracy
    
    def save_checkpoint(
        self,
        epoch: int,
        optimizer: optim.Optimizer,
        val_loss: float,
        is_best: bool = False
    ):
        """Save a training checkpoint."""
        checkpoint = {
            "epoch": epoch,
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "val_loss": val_loss,
            "history": self.history,
            "model_config": {
                "embedding_dim": self.model.embedding_dim,
                "hidden_dims": self.model.hidden_dims,
                "num_classes": self.model.num_classes,
                "dropout": self.model.dropout_rate
            }
        }
        
        # Save latest checkpoint
        torch.save(checkpoint, self.checkpoint_dir / "latest_checkpoint.pt")
        
        # Save best model if this is the best
        if is_best:
            torch.save(checkpoint, self.checkpoint_dir / "best_model.pt")
            # Also save just the model weights for easy loading
            torch.save(
                self.model.state_dict(),
                self.checkpoint_dir / "best_model_weights.pt"
            )
    
    def train(
        self,
        epochs: int = 50,
        learning_rate: float = 0.001,
        weight_decay: float = 1e-4,
        patience: int = 10,
        verbose: bool = True
    ) -> Dict[str, List[float]]:
        """
        Train the model.
        
        Args:
            epochs: Maximum number of epochs
            learning_rate: Learning rate for Adam optimizer
            weight_decay: L2 regularization strength
            patience: Early stopping patience
            verbose: Whether to print progress
            
        Returns:
            Training history dictionary
        """
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(
            self.model.parameters(),
            lr=learning_rate,
            weight_decay=weight_decay
        )
        
        early_stopping = EarlyStopping(patience=patience)
        best_val_loss = float("inf")
        
        print(f"Training on {self.device}")
        print(self.model.get_architecture_summary())
        print(f"\nStarting training for {epochs} epochs...")
        print("-" * 60)
        
        start_time = time.time()
        
        for epoch in range(epochs):
            # Training
            train_loss, train_acc = self.train_epoch(optimizer, criterion)
            
            # Validation
            val_loss, val_acc = self.validate(criterion)
            
            # Record history
            self.history["train_loss"].append(train_loss)
            self.history["val_loss"].append(val_loss)
            self.history["train_acc"].append(train_acc)
            self.history["val_acc"].append(val_acc)
            
            # Check if this is the best model
            is_best = val_loss < best_val_loss
            if is_best:
                best_val_loss = val_loss
            
            # Save checkpoint
            self.save_checkpoint(epoch, optimizer, val_loss, is_best)
            
            # Print progress
            if verbose:
                print(
                    f"Epoch {epoch+1:3d}/{epochs} | "
                    f"Train Loss: {train_loss:.4f} | "
                    f"Train Acc: {train_acc:.4f} | "
                    f"Val Loss: {val_loss:.4f} | "
                    f"Val Acc: {val_acc:.4f}"
                    f"{' *' if is_best else ''}"
                )
            
            # Check early stopping
            if early_stopping(val_loss):
                print(f"\nEarly stopping triggered at epoch {epoch+1}")
                break
        
        elapsed_time = time.time() - start_time
        print("-" * 60)
        print(f"Training completed in {elapsed_time:.1f}s")
        print(f"Best validation loss: {best_val_loss:.4f}")
        
        # Save training history
        with open(self.checkpoint_dir / "training_history.json", "w") as f:
            json.dump(self.history, f, indent=2)
        
        return self.history


def train_model(
    data_path: Optional[str] = None,
    epochs: int = 50,
    batch_size: int = 32,
    learning_rate: float = 0.001,
    patience: int = 10,
    hidden_dims: Optional[List[int]] = None,
    dropout: float = 0.3
) -> Tuple[CommandClassifier, Dict[str, List[float]], DataProcessor]:
    """
    Complete training pipeline.
    
    Args:
        data_path: Path to commands.json
        epochs: Maximum training epochs
        batch_size: Training batch size
        learning_rate: Learning rate
        patience: Early stopping patience
        hidden_dims: Hidden layer dimensions
        dropout: Dropout rate
        
    Returns:
        Tuple of (trained_model, history, data_processor)
    """
    # Prepare data
    print("Loading and preparing data...")
    processor = DataProcessor(data_path)
    train_dataset, val_dataset = processor.prepare_data()
    train_loader, val_loader = processor.create_dataloaders(
        train_dataset, val_dataset, batch_size=batch_size
    )
    
    # Save label mappings
    checkpoint_dir = Path(__file__).parent.parent / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    processor.save_mappings(checkpoint_dir / "label_mappings.json")
    
    # Create model
    model = create_model(
        num_classes=processor.num_classes,
        hidden_dims=hidden_dims,
        dropout=dropout
    )
    
    # Train
    trainer = Trainer(model, train_loader, val_loader)
    history = trainer.train(
        epochs=epochs,
        learning_rate=learning_rate,
        patience=patience
    )
    
    return model, history, processor


if __name__ == "__main__":
    # Run training with default parameters
    model, history, processor = train_model()

