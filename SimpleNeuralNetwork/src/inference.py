"""
Inference Pipeline for Command Classification

Provides a simple interface for classifying astronaut commands
using a trained model. Includes latency benchmarking.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import torch

import sys
sys.path.append(str(Path(__file__).parent.parent))

from models.classifier import CommandClassifier
from src.embeddings import EmbeddingModel


class CommandClassifierInference:
    """
    Inference pipeline for command classification.
    
    Loads a trained model and provides methods for classifying
    commands with confidence scores and latency tracking.
    """
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        mappings_path: Optional[str] = None,
        device: Optional[str] = None
    ):
        """
        Initialize the inference pipeline.
        
        Args:
            model_path: Path to trained model checkpoint
            mappings_path: Path to label mappings JSON
            device: Device to run inference on ('cpu', 'cuda', or None for auto)
        """
        # Set up paths
        checkpoint_dir = Path(__file__).parent.parent / "checkpoints"
        
        if model_path is None:
            model_path = checkpoint_dir / "best_model.pt"
        self.model_path = Path(model_path)
        
        if mappings_path is None:
            mappings_path = checkpoint_dir / "label_mappings.json"
        self.mappings_path = Path(mappings_path)
        
        # Set device
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)
        
        # Load model and mappings
        self._load_model()
        self._load_mappings()
        
        # Initialize embedding model
        self.embedding_model = EmbeddingModel(device=device)
        
        # Latency tracking
        self.last_embedding_time: float = 0.0
        self.last_inference_time: float = 0.0
        self.last_total_time: float = 0.0
    
    def _load_model(self):
        """Load the trained model from checkpoint."""
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model not found at {self.model_path}. "
                "Please train the model first using train.py"
            )
        
        checkpoint = torch.load(self.model_path, map_location=self.device)
        config = checkpoint["model_config"]
        
        self.model = CommandClassifier(
            embedding_dim=config["embedding_dim"],
            hidden_dims=config["hidden_dims"],
            num_classes=config["num_classes"],
            dropout=config["dropout"]
        )
        
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.to(self.device)
        self.model.eval()
        
        print(f"Loaded model from {self.model_path}")
        print(self.model.get_architecture_summary())
    
    def _load_mappings(self):
        """Load intent label mappings."""
        if not self.mappings_path.exists():
            raise FileNotFoundError(
                f"Label mappings not found at {self.mappings_path}"
            )
        
        with open(self.mappings_path, "r") as f:
            mappings = json.load(f)
        
        self.intent_to_idx = mappings["intent_to_idx"]
        self.idx_to_intent = {int(k): v for k, v in mappings["idx_to_intent"].items()}
        self.num_classes = len(self.intent_to_idx)
    
    def classify(
        self,
        command: str,
        return_all_probs: bool = False
    ) -> Dict:
        """
        Classify a single command.
        
        Args:
            command: The command text to classify
            return_all_probs: Whether to return probabilities for all classes
            
        Returns:
            Dictionary containing:
            - intent: Predicted intent name
            - confidence: Confidence score (0-1)
            - latency_ms: Total inference time in milliseconds
            - all_probs: (optional) Dict of all class probabilities
        """
        total_start = time.perf_counter()
        
        # Get embedding
        embed_start = time.perf_counter()
        embedding = self.embedding_model.encode(command)
        embed_time = time.perf_counter() - embed_start
        
        # Run inference
        infer_start = time.perf_counter()
        embedding_tensor = torch.FloatTensor(embedding).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            logits = self.model(embedding_tensor)
            probs = torch.softmax(logits, dim=-1).squeeze()
            confidence, predicted_idx = torch.max(probs, dim=-1)
        
        infer_time = time.perf_counter() - infer_start
        total_time = time.perf_counter() - total_start
        
        # Store latency info
        self.last_embedding_time = embed_time * 1000
        self.last_inference_time = infer_time * 1000
        self.last_total_time = total_time * 1000
        
        # Build result
        result = {
            "command": command,
            "intent": self.idx_to_intent[predicted_idx.item()],
            "confidence": confidence.item(),
            "latency_ms": {
                "embedding": round(self.last_embedding_time, 2),
                "inference": round(self.last_inference_time, 2),
                "total": round(self.last_total_time, 2)
            }
        }
        
        if return_all_probs:
            result["all_probabilities"] = {
                self.idx_to_intent[i]: round(probs[i].item(), 4)
                for i in range(self.num_classes)
            }
        
        return result
    
    def classify_batch(
        self,
        commands: List[str]
    ) -> List[Dict]:
        """
        Classify multiple commands.
        
        Args:
            commands: List of command texts
            
        Returns:
            List of classification results
        """
        total_start = time.perf_counter()
        
        # Get embeddings
        embed_start = time.perf_counter()
        embeddings = self.embedding_model.encode(commands)
        embed_time = time.perf_counter() - embed_start
        
        # Run inference
        infer_start = time.perf_counter()
        embeddings_tensor = torch.FloatTensor(embeddings).to(self.device)
        
        with torch.no_grad():
            logits = self.model(embeddings_tensor)
            probs = torch.softmax(logits, dim=-1)
            confidences, predicted_indices = torch.max(probs, dim=-1)
        
        infer_time = time.perf_counter() - infer_start
        total_time = time.perf_counter() - total_start
        
        # Build results
        results = []
        for i, command in enumerate(commands):
            results.append({
                "command": command,
                "intent": self.idx_to_intent[predicted_indices[i].item()],
                "confidence": confidences[i].item()
            })
        
        # Add timing info to first result
        results[0]["batch_latency_ms"] = {
            "embedding": round(embed_time * 1000, 2),
            "inference": round(infer_time * 1000, 2),
            "total": round(total_time * 1000, 2),
            "per_command": round(total_time * 1000 / len(commands), 2)
        }
        
        return results
    
    def benchmark(
        self,
        commands: List[str],
        num_runs: int = 100
    ) -> Dict:
        """
        Benchmark inference latency.
        
        Args:
            commands: List of test commands
            num_runs: Number of inference runs
            
        Returns:
            Dictionary with latency statistics
        """
        print(f"Running benchmark with {num_runs} iterations...")
        
        embedding_times = []
        inference_times = []
        total_times = []
        
        for _ in range(num_runs):
            for command in commands:
                self.classify(command)
                embedding_times.append(self.last_embedding_time)
                inference_times.append(self.last_inference_time)
                total_times.append(self.last_total_time)
        
        def stats(times):
            return {
                "mean_ms": round(np.mean(times), 2),
                "std_ms": round(np.std(times), 2),
                "min_ms": round(np.min(times), 2),
                "max_ms": round(np.max(times), 2),
                "p95_ms": round(np.percentile(times, 95), 2)
            }
        
        return {
            "num_runs": num_runs * len(commands),
            "embedding": stats(embedding_times),
            "inference": stats(inference_times),
            "total": stats(total_times)
        }
    
    def get_class_names(self) -> List[str]:
        """Get ordered list of class names."""
        return [self.idx_to_intent[i] for i in range(self.num_classes)]


def load_classifier(
    model_path: Optional[str] = None,
    device: Optional[str] = None
) -> CommandClassifierInference:
    """
    Convenience function to load a trained classifier.
    
    Args:
        model_path: Path to model checkpoint
        device: Device for inference
        
    Returns:
        CommandClassifierInference instance
    """
    return CommandClassifierInference(model_path=model_path, device=device)


# Interactive demo
if __name__ == "__main__":
    print("Loading Command Classifier...")
    classifier = load_classifier()
    
    print("\n" + "=" * 60)
    print("ASTRONAUT COMMAND CLASSIFIER - Interactive Demo")
    print("=" * 60)
    print("Type a command and press Enter to classify it.")
    print("Type 'quit' to exit, 'benchmark' to run latency test.\n")
    
    test_commands = [
        "Take me to the oxygen tank",
        "Show diagnostic info for this panel",
        "Increase temperature by 5 degrees",
        "What is the current pressure reading?",
        "Mark this as critical",
        "Record maintenance completed",
        "How do I replace the filter?",
        "Stop current action"
    ]
    
    while True:
        try:
            user_input = input("\nCommand > ").strip()
            
            if user_input.lower() == "quit":
                print("Goodbye!")
                break
            
            if user_input.lower() == "benchmark":
                results = classifier.benchmark(test_commands, num_runs=50)
                print("\nBenchmark Results:")
                print(f"  Total runs: {results['num_runs']}")
                print(f"  Embedding: {results['embedding']['mean_ms']:.1f}ms (±{results['embedding']['std_ms']:.1f}ms)")
                print(f"  Inference: {results['inference']['mean_ms']:.1f}ms (±{results['inference']['std_ms']:.1f}ms)")
                print(f"  Total: {results['total']['mean_ms']:.1f}ms (±{results['total']['std_ms']:.1f}ms)")
                print(f"  P95: {results['total']['p95_ms']:.1f}ms")
                continue
            
            if not user_input:
                continue
            
            result = classifier.classify(user_input, return_all_probs=True)
            
            print(f"\n  Intent: {result['intent']}")
            print(f"  Confidence: {result['confidence']:.2%}")
            print(f"  Latency: {result['latency_ms']['total']:.1f}ms")
            print("\n  All probabilities:")
            
            # Sort by probability
            sorted_probs = sorted(
                result['all_probabilities'].items(),
                key=lambda x: x[1],
                reverse=True
            )
            for intent, prob in sorted_probs:
                bar = "█" * int(prob * 20)
                print(f"    {intent:12s}: {prob:.3f} {bar}")
                
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")

