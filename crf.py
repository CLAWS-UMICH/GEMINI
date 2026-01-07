"""Linear-chain CRF for enforcing valid token label sequences.

Based on pytorch-crf implementation but simplified for our specific use case.
"""

from __future__ import annotations

import torch
import torch.nn as nn


class CRF(nn.Module):
    """Conditional Random Field layer.

    Enforces valid transitions between token labels:
    - START can only be followed by CONT or TEXT
    - CONT can only be followed by CONT or TEXT
    - TEXT can be followed by anything

    This prevents invalid sequences like START-START.
    """

    def __init__(self, num_tags: int, batch_first: bool = True):
        """Initialize CRF.

        Args:
            num_tags: Number of token labels (3: TEXT, START, CONT)
            batch_first: If True, expects (batch, seq_len, num_tags)
        """
        super().__init__()
        self.num_tags = num_tags
        self.batch_first = batch_first

        # Transition scores: transitions[i, j] = score of transitioning from tag i to tag j
        self.transitions = nn.Parameter(torch.randn(num_tags, num_tags))

        # Start and end transitions (for BOS and EOS)
        self.start_transitions = nn.Parameter(torch.randn(num_tags))
        self.end_transitions = nn.Parameter(torch.randn(num_tags))

        self.reset_parameters()

    def reset_parameters(self):
        """Initialize parameters with constraint-aware values."""
        nn.init.uniform_(self.transitions, -0.1, 0.1)
        nn.init.uniform_(self.start_transitions, -0.1, 0.1)
        nn.init.uniform_(self.end_transitions, -0.1, 0.1)

    def forward(self, emissions: torch.Tensor, tags: torch.LongTensor, mask: torch.ByteTensor) -> torch.Tensor:
        """Compute negative log-likelihood loss.

        Args:
            emissions: (batch, seq_len, num_tags) - logits from model
            tags: (batch, seq_len) - ground truth labels
            mask: (batch, seq_len) - 1 for valid positions, 0 for padding

        Returns:
            Negative log-likelihood loss (scalar)
        """
        if self.batch_first:
            emissions = emissions.transpose(0, 1)  # (seq_len, batch, num_tags)
            tags = tags.transpose(0, 1)            # (seq_len, batch)
            mask = mask.transpose(0, 1)            # (seq_len, batch)

        # Compute log partition function (normalization)
        log_partition = self._compute_log_partition(emissions, mask)

        # Compute score of gold sequence
        gold_score = self._compute_score(emissions, tags, mask)

        # NLL = log(Z) - score(gold)
        return torch.mean(log_partition - gold_score)

    def decode(self, emissions: torch.Tensor, mask: torch.ByteTensor) -> list[list[int]]:
        """Find most likely tag sequence using Viterbi algorithm.

        Args:
            emissions: (batch, seq_len, num_tags) - logits from model
            mask: (batch, seq_len) - 1 for valid positions, 0 for padding

        Returns:
            List of predicted tag sequences (one per batch item)
        """
        if self.batch_first:
            emissions = emissions.transpose(0, 1)  # (seq_len, batch, num_tags)
            mask = mask.transpose(0, 1)            # (seq_len, batch)

        return self._viterbi_decode(emissions, mask)

    def _compute_score(self, emissions: torch.Tensor, tags: torch.LongTensor, mask: torch.ByteTensor) -> torch.Tensor:
        """Compute score of a given tag sequence.

        Score = sum of emission scores + sum of transition scores
        """
        seq_len, batch_size = tags.shape

        # Start transition score
        score = self.start_transitions[tags[0]]  # (batch,)

        # Emission score for first tag
        score += emissions[0].gather(1, tags[0].unsqueeze(1)).squeeze(1)  # (batch,)

        # Transition and emission scores for remaining tags
        for i in range(1, seq_len):
            # Only add score where mask is 1
            score += torch.where(
                mask[i].bool(),
                self.transitions[tags[i - 1], tags[i]] + emissions[i].gather(1, tags[i].unsqueeze(1)).squeeze(1),
                torch.zeros_like(score)
            )

        # End transition score (only for last valid position)
        seq_lens = mask.sum(dim=0)  # (batch,)
        last_tags = tags.gather(0, (seq_lens - 1).unsqueeze(0)).squeeze(0)  # (batch,)
        score += self.end_transitions[last_tags]

        return score

    def _compute_log_partition(self, emissions: torch.Tensor, mask: torch.ByteTensor) -> torch.Tensor:
        """Compute log partition function using forward algorithm.

        This sums over all possible tag sequences.
        """
        seq_len, batch_size, num_tags = emissions.shape

        # Initialize with start transitions + first emissions
        alpha = self.start_transitions + emissions[0]  # (batch, num_tags)

        # Forward pass
        for i in range(1, seq_len):
            # Broadcast: (batch, num_tags, 1) + (num_tags, num_tags) + (batch, 1, num_tags)
            # Result: (batch, num_tags, num_tags) representing all possible transitions
            emit_score = emissions[i].unsqueeze(1)  # (batch, 1, num_tags)
            trans_score = self.transitions.unsqueeze(0)  # (1, num_tags, num_tags)
            next_alpha = alpha.unsqueeze(2) + trans_score + emit_score  # (batch, num_tags, num_tags)

            # Log-sum-exp over previous tags
            next_alpha = torch.logsumexp(next_alpha, dim=1)  # (batch, num_tags)

            # Apply mask
            alpha = torch.where(mask[i].unsqueeze(1).bool(), next_alpha, alpha)

        # Add end transitions
        alpha = alpha + self.end_transitions.unsqueeze(0)

        # Log partition = log-sum-exp over all final tags
        return torch.logsumexp(alpha, dim=1)  # (batch,)

    def _viterbi_decode(self, emissions: torch.Tensor, mask: torch.ByteTensor) -> list[list[int]]:
        """Viterbi algorithm to find most likely sequence.

        Instead of summing over all paths (forward), we take the max.
        """
        seq_len, batch_size, num_tags = emissions.shape

        # Initialize
        viterbi = self.start_transitions + emissions[0]  # (batch, num_tags)
        backpointers = []

        # Forward pass
        for i in range(1, seq_len):
            # (batch, num_tags, 1) + (num_tags, num_tags) + (batch, 1, num_tags)
            next_scores = viterbi.unsqueeze(2) + self.transitions.unsqueeze(0) + emissions[i].unsqueeze(1)

            # Take max over previous tags (instead of log-sum-exp)
            next_viterbi, next_backpointers = next_scores.max(dim=1)

            # Apply mask
            viterbi = torch.where(mask[i].unsqueeze(1).bool(), next_viterbi, viterbi)
            backpointers.append(next_backpointers)

        # Add end transitions
        viterbi = viterbi + self.end_transitions.unsqueeze(0)

        # Backtrack to find best path
        best_tags_list = []
        for batch_idx in range(batch_size):
            # Find best last tag
            seq_len_i = mask[:, batch_idx].sum().item()
            _, best_last_tag = viterbi[batch_idx].max(dim=0)
            best_tags = [best_last_tag.item()]

            # Backtrack
            for bp in reversed(backpointers[:seq_len_i - 1]):
                best_last_tag = bp[batch_idx, best_tags[-1]]
                best_tags.append(best_last_tag.item())

            best_tags.reverse()
            best_tags_list.append(best_tags[:seq_len_i])

        return best_tags_list


def create_transition_constraints(label2id: dict[str, int]) -> torch.Tensor:
    """Create transition constraint matrix.

    Returns a mask where:
    - 0 = forbidden transition (will be set to -inf)
    - 1 = allowed transition

    Valid transitions:
    - TEXT -> anything (TEXT, START, CONT)
    - START -> CONT or TEXT (NOT START)
    - CONT -> CONT or TEXT (NOT START)
    """
    num_tags = len(label2id)
    constraints = torch.ones(num_tags, num_tags)

    # Get indices
    text_idx = label2id.get("TEXT", -1)
    start_idx = label2id.get("TASK_NAME_START", -1)
    cont_idx = label2id.get("TASK_NAME_CONT", -1)

    if start_idx != -1 and cont_idx != -1:
        # START -> START is forbidden
        constraints[start_idx, start_idx] = 0

        # CONT -> START is forbidden
        constraints[cont_idx, start_idx] = 0

    return constraints


def apply_transition_constraints(crf: CRF, constraints: torch.Tensor):
    """Apply hard constraints to CRF transitions.

    Sets forbidden transitions to -10000 (effectively -inf).
    """
    with torch.no_grad():
        # Where constraint is 0, set transition to very negative
        crf.transitions.data = torch.where(
            constraints.bool(),
            crf.transitions.data,
            torch.tensor(-10000.0)
        )
