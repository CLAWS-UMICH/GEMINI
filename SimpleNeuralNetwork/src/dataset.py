"""
Dataset utilities for loading and preprocessing astronaut commands.

Handles loading from JSON, creating train/validation splits, and
preparing data for PyTorch training.
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import train_test_split

from .embeddings import EmbeddingModel


class CommandDataset(Dataset):
    """
    PyTorch Dataset for astronaut command classification.
    
    Stores pre-computed embeddings and intent labels for efficient training.
    """
    
    def __init__(
        self,
        embeddings: np.ndarray,
        labels: np.ndarray,
        texts: Optional[List[str]] = None
    ):
        """
        Initialize the dataset.
        
        Args:
            embeddings: Pre-computed embeddings of shape (n_samples, embedding_dim)
            labels: Integer labels of shape (n_samples,)
            texts: Optional list of original text commands
        """
        self.embeddings = torch.FloatTensor(embeddings)
        self.labels = torch.LongTensor(labels)
        self.texts = texts
    
    def __len__(self) -> int:
        return len(self.labels)
    
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        return self.embeddings[idx], self.labels[idx]
    
    def get_text(self, idx: int) -> Optional[str]:
        """Get the original text for an index."""
        if self.texts is not None:
            return self.texts[idx]
        return None


class DataProcessor:
    """
    Processes the raw command dataset and prepares it for training.
    
    Handles:
    - Loading JSON dataset
    - Creating intent-to-index mappings
    - Computing embeddings
    - Creating train/validation splits
    """
    
    def __init__(
        self,
        data_path: Optional[str] = None,
        embedding_model: Optional[EmbeddingModel] = None
    ):
        """
        Initialize the data processor.
        
        Args:
            data_path: Path to commands.json file
            embedding_model: EmbeddingModel instance (creates new one if None)
        """
        if data_path is None:
            data_path = Path(__file__).parent.parent / "data" / "commands.json"
        self.data_path = Path(data_path)
        
        if embedding_model is None:
            embedding_model = EmbeddingModel()
        self.embedding_model = embedding_model
        
        # Will be populated when data is loaded
        self.intent_to_idx: Dict[str, int] = {}
        self.idx_to_intent: Dict[int, str] = {}
        self.num_classes: int = 0
    
    def load_data(self) -> Tuple[List[str], List[str]]:
        """
        Load the dataset from JSON.
        
        Returns:
            Tuple of (texts, intents) where:
            - texts: List of command strings
            - intents: List of intent names
        """
        with open(self.data_path, "r") as f:
            data = json.load(f)
        
        texts = []
        intents = []
        
        # Build intent mappings and collect data
        for idx, intent_data in enumerate(data["intents"]):
            intent_name = intent_data["intent"]
            self.intent_to_idx[intent_name] = idx
            self.idx_to_intent[idx] = intent_name
            
            for example in intent_data["examples"]:
                texts.append(example)
                intents.append(intent_name)
        
        self.num_classes = len(self.intent_to_idx)
        return texts, intents
    
    def prepare_data(
        self,
        test_size: float = 0.2,
        random_state: int = 42,
        show_progress: bool = True
    ) -> Tuple[CommandDataset, CommandDataset]:
        """
        Prepare training and validation datasets.
        
        Args:
            test_size: Fraction of data for validation
            random_state: Random seed for reproducibility
            show_progress: Whether to show embedding progress
            
        Returns:
            Tuple of (train_dataset, val_dataset)
        """
        # Load raw data
        texts, intents = self.load_data()
        
        # Convert intents to indices
        labels = np.array([self.intent_to_idx[intent] for intent in intents])
        
        # Compute embeddings
        print("Computing embeddings...")
        embeddings = self.embedding_model.encode(texts, show_progress=show_progress)
        
        # Split data
        (
            train_embeddings, val_embeddings,
            train_labels, val_labels,
            train_texts, val_texts
        ) = train_test_split(
            embeddings, labels, texts,
            test_size=test_size,
            random_state=random_state,
            stratify=labels  # Ensure balanced split
        )
        
        # Create datasets
        train_dataset = CommandDataset(train_embeddings, train_labels, train_texts)
        val_dataset = CommandDataset(val_embeddings, val_labels, val_texts)
        
        print(f"Training samples: {len(train_dataset)}")
        print(f"Validation samples: {len(val_dataset)}")
        print(f"Number of classes: {self.num_classes}")
        
        return train_dataset, val_dataset
    
    def create_dataloaders(
        self,
        train_dataset: CommandDataset,
        val_dataset: CommandDataset,
        batch_size: int = 32,
        num_workers: int = 0
    ) -> Tuple[DataLoader, DataLoader]:
        """
        Create DataLoaders for training.
        
        Args:
            train_dataset: Training dataset
            val_dataset: Validation dataset
            batch_size: Batch size for training
            num_workers: Number of data loading workers
            
        Returns:
            Tuple of (train_loader, val_loader)
        """
        train_loader = DataLoader(
            train_dataset,
            batch_size=batch_size,
            shuffle=True,
            num_workers=num_workers
        )
        
        val_loader = DataLoader(
            val_dataset,
            batch_size=batch_size,
            shuffle=False,
            num_workers=num_workers
        )
        
        return train_loader, val_loader
    
    def get_class_names(self) -> List[str]:
        """Get list of class names in order."""
        return [self.idx_to_intent[i] for i in range(self.num_classes)]
    
    def save_mappings(self, path: str):
        """Save intent mappings to JSON."""
        mappings = {
            "intent_to_idx": self.intent_to_idx,
            "idx_to_intent": {str(k): v for k, v in self.idx_to_intent.items()}
        }
        with open(path, "w") as f:
            json.dump(mappings, f, indent=2)
    
    def load_mappings(self, path: str):
        """Load intent mappings from JSON."""
        with open(path, "r") as f:
            mappings = json.load(f)
        self.intent_to_idx = mappings["intent_to_idx"]
        self.idx_to_intent = {int(k): v for k, v in mappings["idx_to_intent"].items()}
        self.num_classes = len(self.intent_to_idx)

