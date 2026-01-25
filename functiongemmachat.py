# pip install -U mlx-lm


from mlx_lm import load, stream_generate
from dotenv import load_dotenv
import os, time

load_dotenv()

# Best speed/memory on Apple Silicon:
# (bf16 also exists: mlx-community/functiongemma-270m-it-bf16)
model_id = "mlx-community/functiongemma-270m-it-bf16"

# If the repo is gated, make sure HF_TOKEN is set
# (mlx-lm uses HF Hub under the hood)
hf_token = os.getenv("HUGGING_FACE_TOKEN")
if hf_token:
    os.environ["HF_TOKEN"] = hf_token

print(f"Loading {model_id}...")
model, tokenizer = load(model_id)

weather_function_schema = {
    "type": "function",
    "function": {
        "name": "get_current_temperature",
        "description": "Gets the current temperature for a given location.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "The city name, e.g. San Francisco"},
            },
            "required": ["location"],
        },
    },
}

# Prefer "system" for HF chat templates
messages = [
    {"role": "system", "content": "You are a model that can do function calling with the following functions"},
    {"role": "user", "content": "What's the temperature in London?"},
]

# Some tokenizers support tools=... in apply_chat_template; keep a safe fallback.
try:
    prompt = tokenizer.apply_chat_template(
        messages,
        tools=[weather_function_schema],
        add_generation_prompt=True,
    )
except TypeError:
    # Fallback: embed tool schema into the system message
    messages[0]["content"] += f"\n\nFunctions:\n{weather_function_schema}"
    prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True)

print("Response:", end=" ", flush=True)

generated_text = ""
start_time = time.time()

# MLX-LM streaming API
for resp in stream_generate(model, tokenizer, prompt, max_tokens=128):
    # resp.text is the incremental chunk
    print(resp.text, end="", flush=True)
    generated_text += resp.text

duration = time.time() - start_time
total_tokens = len(tokenizer.encode(generated_text))
tps = total_tokens / duration if duration > 0 else 0.0

print("\n\nMetrics:")
print(f"Model: {model_id}")
print(f"Tokens generated: {total_tokens}")
print(f"Time taken: {duration:.2f}s")
print(f"TPS: {tps:.2f}")
