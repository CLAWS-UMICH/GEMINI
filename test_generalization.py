
import sys
import torch
from simplechat import load_model, classify

def test_prompts():
    print("Loading model for testing...")
    model, tokenizer, tool_labels, token_labels, device, has_threshold = load_model()
    
    test_cases = [
        {
            "prompt": "make a task to walk the dog and add a waypoint at the room",
            "expected_intent": ["Add_task", "Add_waypoint"],
            "expected_tokens": {"room": "WAYPOINT_NAME", "walk the dog": "TASK_NAME"}
        },
        {
            "prompt": "add a task",
            "expected_intent": ["Add_task"],
            "expected_tokens": {} 
        },
        {
            "prompt": "make a waypoint",
            "expected_intent": ["Add_waypoint"],
            "expected_tokens": {}
        },
        {
            "prompt": "make a waypoint at the rock",
            "expected_intent": ["Add_waypoint"],
            "expected_tokens": {"rock": "WAYPOINT_NAME"}
        },
        {
            "prompt": "delete the map point for the big rock",
            "expected_intent": ["delete_waypoint"], # Note: might be DELETE_WAYPOINT or delete_waypoint depending on labels
            "expected_tokens": {"big rock": "WAYPOINT_NAME", "map point": "TEXT"} # map point shouldn't be TASK_NAME
        }
    ]

    print("\n" + "="*60)
    print("RUNNING GENERALIZATION TESTS")
    print("="*60)

    for case in test_cases:
        prompt = case["prompt"]
        print(f"\nPrompt: '{prompt}'")
        
        pred_tags, all_tags, token_results, threshold = classify(
            prompt, model, tokenizer, tool_labels, token_labels, device, has_threshold
        )
        
        # Analyze Intents
        predicted_intents = [t[0] for t in pred_tags]
        print(f"  Predicted Intents: {predicted_intents} (Expected: {case['expected_intent']})")
        
        # Analyze Tokens
        print("  Token Labels:")
        extracted_entities = {}
        for tok, label in token_results:
            clean_tok = tok.replace("##", "")
            if label != "TEXT":
                 print(f"    {clean_tok}: {label}")
                 # Simple extraction for checking (not perfect reconstruction but good enough for token checks)
        
        # Manually check expectations (soft check output)
        match = True
        for exp_int in case["expected_intent"]:
            if exp_int not in predicted_intents:
                # Allow for casing mismatch if logic allows, but here we expect exact match
                # Check if we have standardizes labels
                if exp_int == "delete_waypoint" and "DELETE_WAYPOINT" in predicted_intents:
                     pass # Accept legacy if present, but we prefer consistency
                else:
                    match = False
        
        if match:
             print("\n  [PASS] Intents match expectations")
        else:
             print("\n  [FAIL] Intent mismatch")

if __name__ == "__main__":
    test_prompts()
