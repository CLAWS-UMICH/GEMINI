import os
import json
from google import genai
from pydantic import BaseModel, Field

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
MODEL = "gemini-2.5-flash"   # or "gpt-4o-mini" if you're routing via some proxy
NUM_SAMPLES_PER_INPUT = 5    # How many synthetic examples per input
# ------------------------------------------------------------

client = genai.Client()

SYSTEM_PROMPT = """

You generate synthetic training data for an intent classification model.
Given a list of (command, label), you must create *new* commands that:

- are natural variations of the original
- keep the meaning and intent consistent with the label
- avoid simply rephrasing using synonyms; instead introduce realistic diversity
- avoid contradictions or ambiguous phrasing
- return output as JSON only:
  [{"command": "...", "label": "..."}, ...]

return output as JSON only:
  [{"": "show me oxygen levels", "label": "oxygen"}, 
   {"": "show me temperature values", "label": "temp"]
"""
class Command(BaseModel):
    command: str = Field(description="command from astronaut")
    label: str = Field(description="basic label for command")

def generate_synthetic_examples(examples, num_samples_per_input=NUM_SAMPLES_PER_INPUT):
    """
    examples: list of dicts like:
        [{"command": "turn on the lights", "label": "activate_lights"}, ...]

    returns: list of synthetic examples
    """

    user_prompt = (
        "Generate synthetic variations for these labeled commands:\n\n"
        + json.dumps(examples, indent=2)
        + f"\n\nFor each input example, produce exactly {num_samples_per_input} new examples."
    )

    # ✅ Use system + user prompts
    # ✅ Ask for JSON via response_mime_type
    response = client.models.generate_content(
        model=MODEL,
        contents=SYSTEM_PROMPT,
        config={"response_mime_type" : "application/json",
            "response_json_schema" : Command.model_json_schema()
            }
    )

    # With response_mime_type="application/json",
    # response.text should now be a JSON string.
    try:
        data = json.loads(response.text)
        return data
    except Exception:
        print("❗ Failed to decode model output. Raw response:")
        print(repr(response.text))
        # Optional: inspect the full object if needed
        # print(response)
        raise


# ------------------------------------------------------------
# Example usage
# ------------------------------------------------------------
if __name__ == "__main__":
    seed_examples = [
        {"command": "turn on the cabin lights", "label": "activate_lights"},
        {"command": "open the airlock door", "label": "open_airlock"},
        {"command": "play the mission briefing", "label": "play_audio"},
    ]

    synthetic = generate_synthetic_examples(seed_examples)
    print("\n=== Synthetic Data ===")
    print(json.dumps(synthetic, indent=2))
