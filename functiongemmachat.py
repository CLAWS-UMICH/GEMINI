# from transformers import AutoProcessor, AutoModelForCausalLM, TextIteratorStreamer
# import torch
# from threading import Thread
# import time
# from dotenv import load_dotenv
# import os

# load_dotenv()

# # Load the model and processor
# model_id = "google/functiongemma-270m-it"
# print(f"Loading {model_id}...")

# # device_map="auto" will use GPU if available, otherwise CPU
# # Using the token provided in previous step
# processor = AutoProcessor.from_pretrained(model_id, device_map="auto", HF_TOKEN=os.getenv("HUGGING_FACE_TOKEN"))
# model = AutoModelForCausalLM.from_pretrained(model_id, dtype="auto", device_map="auto")

# # Define a simple tool (function) schema
# weather_function_schema = {
#     "type": "function",
#     "function": {
#         "name": "get_current_temperature",
#         "description": "Gets the current temperature for a given location.",
#         "parameters": {
#             "type": "object",
#             "properties": {
#                 "location": {
#                     "type": "string",
#                     "description": "The city name, e.g. San Francisco",
#                 },
#             },
#             "required": ["location"],
#         },
#     }
# }

# # Create the message with the essential developer prompt
# messages = [
#     {
#         "role": "developer",
#         "content": "You are a model that can do function calling with the following functions"
#     },
#     {
#         "role": "user", 
#         "content": "What's the temperature in London?"
#     }
# ]

# print("Sending prompt...")
# # Prepare inputs
# inputs = processor.apply_chat_template(
#     messages, 
#     tools=[weather_function_schema], 
#     add_generation_prompt=True, 
#     return_dict=True, 
#     return_tensors="pt"
# )

# # Move inputs to the same device as the model
# inputs = inputs.to(model.device)

# # Get tokenizer (handle if processor wraps it)
# # For FunctionGemma, the processor usually contains the tokenizer or behaves like one.
# # We try to get the tokenizer attribute, otherwise use the processor itself.
# tokenizer = getattr(processor, "tokenizer", processor)

# # Setup streamer
# streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)

# # Generate response in a separate thread
# generation_kwargs = dict(**inputs, streamer=streamer, max_new_tokens=128, pad_token_id=tokenizer.eos_token_id)
# thread = Thread(target=model.generate, kwargs=generation_kwargs)
# thread.start()

# print("Response:", end=" ", flush=True)

# # Consume the stream and measure performance
# generated_text = ""
# start_time = time.time()

# for new_text in streamer:
#     print(new_text, end="", flush=True)
#     generated_text += new_text

# end_time = time.time()
# duration = end_time - start_time

# # Calculate tokens and TPS
# # We encode the generated text to count tokens accurately
# total_tokens = len(tokenizer.encode(generated_text))
# tps = total_tokens / duration if duration > 0 else 0

# print(f"\n\nMetrics:")
# print(f"Tokens generated: {total_tokens}")
# print(f"Time taken: {duration:.2f}s")
# print(f"TPS: {tps:.2f}")


from transformers import AutoProcessor, AutoModelForCausalLM, TextIteratorStreamer
import torch
from threading import Thread
import time
from dotenv import load_dotenv
import os

load_dotenv()

model_id = "google/functiongemma-270m-it"
hf_token = os.getenv("HUGGING_FACE_TOKEN")

print(f"Loading {model_id}...")

# ---- Apple Silicon / device selection ----
if torch.backends.mps.is_available():
    device = torch.device("mps")
    torch_dtype = torch.float16  # best perf on M-series
elif torch.cuda.is_available():
    device = torch.device("cuda")
    torch_dtype = torch.float16
else:
    device = torch.device("cpu")
    torch_dtype = torch.float32

# Optional: reduce CPU overhead during tokenization / small ops
torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))

# Processor/tokenizer (note: AutoProcessor does not need device_map)
processor = AutoProcessor.from_pretrained(model_id, token=hf_token)

# Model: avoid device_map on mac; explicitly move to MPS
# attn_implementation="sdpa" can be faster when supported; if it errors, remove it.
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    token=hf_token,
    torch_dtype=torch_dtype,
    low_cpu_mem_usage=True,
    attn_implementation="sdpa",
)
model.to(device)
model.eval()

# ---- Tool schema ----
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

messages = [
    {"role": "developer", "content": "You are a model that can do function calling with the following functions"},
    {"role": "user", "content": "What's the temperature in London?"},
]

print("Sending prompt...")

inputs = processor.apply_chat_template(
    messages,
    tools=[weather_function_schema],
    add_generation_prompt=True,
    return_dict=True,
    return_tensors="pt",
)

# Move tensors to the same device as the model (MPS on Mac)
inputs = inputs.to(device)

tokenizer = getattr(processor, "tokenizer", processor)

streamer = TextIteratorStreamer(
    tokenizer,
    skip_prompt=True,
    skip_special_tokens=True,
)

pad_id = tokenizer.eos_token_id if tokenizer.eos_token_id is not None else tokenizer.pad_token_id

# ---- Warmup (helps stabilize timing on MPS) ----
with torch.inference_mode():
    _ = model.generate(**inputs, max_new_tokens=1, do_sample=False, use_cache=True, pad_token_id=pad_id)
if device.type == "mps":
    torch.mps.synchronize()

generation_kwargs = dict(
    **inputs,
    streamer=streamer,
    max_new_tokens=128,
    do_sample=False,      # faster than sampling
    use_cache=True,       # important for decoder-only speed
    pad_token_id=pad_id,
)

def _generate():
    with torch.inference_mode():
        model.generate(**generation_kwargs)
    if device.type == "mps":
        torch.mps.synchronize()

thread = Thread(target=_generate)
thread.start()

print("Response:", end=" ", flush=True)

generated_text = ""
if device.type == "mps":
    torch.mps.synchronize()
start_time = time.time()

for new_text in streamer:
    print(new_text, end="", flush=True)
    generated_text += new_text

thread.join()
if device.type == "mps":
    torch.mps.synchronize()
end_time = time.time()

duration = end_time - start_time

# Token count (still easiest to compute from text when streaming)
total_tokens = len(tokenizer.encode(generated_text))
tps = total_tokens / duration if duration > 0 else 0

print(f"\n\nMetrics:")
print(f"Device: {device} | dtype: {torch_dtype}")
print(f"Tokens generated: {total_tokens}")
print(f"Time taken: {duration:.2f}s")
print(f"TPS: {tps:.2f}")
