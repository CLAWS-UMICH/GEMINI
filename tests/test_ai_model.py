
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_model import IntentClassifier

# Test 1: Basic vitals command
def test_classift_vitals():
    """Test 'check my vitals' returns correct intent."""

    mappings = {
        "vitals": "check_vitals",
        "oxygen": "check_oxygen_level",
        "battery": "check_battery"
    }

    classifier = IntentClassifier(mappings)

    result = classifier.classify("check my vitals")

    print(f"Result: {result}")
    
    assert result["intent"] == "check_vitals"
    assert result["confidence"] > 0.0
    assert len(result["matched_keywords"]) > 0

