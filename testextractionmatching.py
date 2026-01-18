import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

def get_embedding(text, tokenizer, model):
    """
    Get the mean pooled embedding for a full text string.
    """
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        outputs = model(**inputs)
    
    # Last hidden state: (batch_size, seq_len, hidden_size)
    last_hidden_state = outputs.last_hidden_state
    
    # Exclude [CLS] and [SEP] for mean pooling (indices 1:-1)
    # Actually, proper attention masking is safer
    attention_mask = inputs['attention_mask']
    
    # Mask padding tokens
    # Expand mask to match hidden state dimensions
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    
    # Sum embeddings
    sum_embeddings = torch.sum(last_hidden_state * input_mask_expanded, 1)
    sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
    
    return sum_embeddings / sum_mask

def main():
    # 1. Load Model (matching the one used in simpletrain.py)
    model_name = "distilbert-base-uncased"
    print(f"Loading model: {model_name}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()

    # 2. Input Sentence Processing
    sentence = "mark the rock task as done, the big one"
    target_word = "rock"
    
    # Tokenize sentence
    inputs = tokenizer(sentence, return_tensors="pt")
    tokens = tokenizer.convert_ids_to_tokens(inputs['input_ids'][0])
    
    print(f"\nSentence: '{sentence}'")
    print(f"Tokens: {tokens}")

    # Find the index of the tokens corresponding to "rock"
    # Note: This simple search assumes "rock" is contiguous and present
    target_indices = []
    # Simple search for the target word tokens
    # We strip ## because tokens might be subwords, but "rock" is likely whole
    # We look for the sequence of tokens that form "rock"
    
    # Naive search for single tokens or subword sequences matching the target
    # Ideally we'd use offset_mapping, but for this specific "rock" example, let's manual scan
    # or use offset mapping properly.
    
    inputs_with_offsets = tokenizer(sentence, return_tensors="pt", return_offsets_mapping=True)
    offsets = inputs_with_offsets["offset_mapping"][0]
    input_ids = inputs_with_offsets["input_ids"]
    
    # Find spans that overlap with "rock" in the original string
    start_char = sentence.find(target_word)
    end_char = start_char + len(target_word)
    
    if start_char == -1:
        print(f"Error: '{target_word}' not found in sentence.")
        return

    print(f"Target '{target_word}' found at char indices {start_char}-{end_char}")
    
    target_token_indices = []
    for idx, (o_start, o_end) in enumerate(offsets):
        # Check if this token overlaps with the target word char span
        # Distilbert special tokens have (0,0) usually, check!
        if o_start == o_end: 
            continue
            
        # If the token is mainly within the char range
        # (o_start < end_char) and (o_end > start_char)
        if o_start < end_char and o_end > start_char:
            target_token_indices.append(idx)

    print(f"Target token indices: {target_token_indices}")
    display_tokens = [tokens[i] for i in target_token_indices]
    print(f"Target tokens: {display_tokens}")

    # Get Embeddings for the sentence
    with torch.no_grad():
        outputs = model(**inputs)
    
    last_hidden_state = outputs.last_hidden_state # (1, seq_len, hidden_dim)
    
    # Extract specific token embeddings and average them
    target_embedding = last_hidden_state[0, target_token_indices, :].mean(dim=0) # (hidden_dim)
    
    # 3. Candidate Task Names
    candidates = [
        "Big Rock",
        "Replace Fuse", 
        "Check Pressure", 
        "Orbit Adjustment", 
        "Prepare EVA",
        "Geological Survey",
        "Small Rock"
    ]
    
    print(f"\nComparing '{target_word}' (contextualized) to candidates...")
    
    scores = []
    for cand in candidates:
        # For candidates, we treat them as independent phrases
        # We can use Mean Pooling over the candidate phrase
        cand_embed = get_embedding(cand, tokenizer, model)[0] # (hidden_dim)
        
        # Cosine Similarity
        similarity = F.cosine_similarity(target_embedding.unsqueeze(0), cand_embed.unsqueeze(0))
        scores.append((cand, similarity.item()))
    
    # 4. Rank and Print
    scores.sort(key=lambda x: x[1], reverse=True)
    
    print("\nResults (Cosine Similarity):")
    print("-" * 40)
    for name, score in scores:
        print(f"{score:.4f} | {name}")
    print("-" * 40)

if __name__ == "__main__":
    main()
