from transformers import AutoProcessor, AutoModelForCausalLM, TextIteratorStreamer
import torch
from threading import Thread
import time
from dotenv import load_dotenv
import os

load_dotenv()

# Load the model and processor
model_id = "google/functiongemma-270m-it"
print(f"Loading {model_id}...")

# device_map="auto" will use GPU if available, otherwise CPU
# Using the token provided in previous step
processor = AutoProcessor.from_pretrained(model_id, device_map="auto", HF_TOKEN=os.getenv("HUGGING_FACE_TOKEN"))
model = AutoModelForCausalLM.from_pretrained(model_id, dtype="auto", device_map="auto")

# Define a simple tool (function) schema
weather_function_schema = {
    "type": "function",
    "function": {
        "name": "get_current_temperature",
        "description": "Gets the current temperature for a given location.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city name, e.g. San Francisco",
                },
            },
            "required": ["location"],
        },
    }
}

# Create the message with the essential developer prompt
messages = [
    {
        "role": "developer",
        "content": "You are a model that can do function calling with the following functions"
    },
    {
        "role": "user", 
        "content": "What's the temperature in London?"
    }
]

print("Sending prompt...")
# Prepare inputs
inputs = processor.apply_chat_template(
    messages, 
    tools=[weather_function_schema], 
    add_generation_prompt=True, 
    return_dict=True, 
    return_tensors="pt"
)

# Move inputs to the same device as the model
inputs = inputs.to(model.device)

# Get tokenizer (handle if processor wraps it)
# For FunctionGemma, the processor usually contains the tokenizer or behaves like one.
# We try to get the tokenizer attribute, otherwise use the processor itself.
tokenizer = getattr(processor, "tokenizer", processor)

# Setup streamer
streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)

# Generate response in a separate thread
generation_kwargs = dict(**inputs, streamer=streamer, max_new_tokens=128, pad_token_id=tokenizer.eos_token_id)
thread = Thread(target=model.generate, kwargs=generation_kwargs)
thread.start()

print("Response:", end=" ", flush=True)

# Consume the stream and measure performance
generated_text = ""
start_time = time.time()

for new_text in streamer:
    print(new_text, end="", flush=True)
    generated_text += new_text

end_time = time.time()
duration = end_time - start_time

# Calculate tokens and TPS
# We encode the generated text to count tokens accurately
total_tokens = len(tokenizer.encode(generated_text))
tps = total_tokens / duration if duration > 0 else 0

print(f"\n\nMetrics:")
print(f"Tokens generated: {total_tokens}")
print(f"Time taken: {duration:.2f}s")
print(f"TPS: {tps:.2f}")
