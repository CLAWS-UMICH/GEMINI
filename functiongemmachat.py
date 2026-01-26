# pip install -U mlx-lm transformers torch python-dotenv
# On Apple Silicon Mac: uses MLX
# Elsewhere: uses Transformers CPU fallback

from dotenv import load_dotenv
import os, time, sys, platform, json

load_dotenv()

hf_token = os.getenv("HUGGING_FACE_TOKEN")
if hf_token:
    os.environ["HF_TOKEN"] = hf_token

# ----------------------------
# Detect Apple Silicon Mac -> use MLX
# Otherwise -> CPU via Transformers
# ----------------------------
is_apple_silicon_mac = (sys.platform == "darwin" and platform.machine().lower() in ("arm64", "aarch64"))

USE_MLX = False
if is_apple_silicon_mac:
    try:
        from mlx_lm import load as mlx_load, stream_generate as mlx_stream_generate
        USE_MLX = True
    except Exception:
        USE_MLX = False

MLX_MODEL_ID = "mlx-community/functiongemma-270m-it-bf16"
HF_MODEL_ID  = "google/functiongemma-270m-it"

# ----------------------------
# Two tools
# ----------------------------
get_temperature_schema = {
    "type": "function",
    "function": {
        "name": "get_temperature",
        "description": "Fetches the user's body temperature in degrees Fahrenheit (°F).",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

add_task_schema = {
    "type": "function",
    "function": {
        "name": "add_task",
        "description": "Creates a task/reminder in a task system.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "due": {"type": "string"},
                "notes": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["title"],
        },
    },
}

tools = [get_temperature_schema, add_task_schema]

# ----------------------------
# Prefilled calls + outputs for Query 2
# ----------------------------
SYSTEM_PROMPT = (
    "Answer in EXACTLY ONE SHORT PLAIN TEXT SENTENCE. No markdown. No bolding. No JSON.\n"
    "If the temperature label is 'fever-range', say the user is unhealthy or has a fever."
)

messages_1 = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "Can you get my temperature, tell me if I'm healthy, and also make a task to inspect the rock?"},
]

messages_2 = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "Can you get my temperature and tell me if I'm healthy? Also make a task to inspect the rock. BE SURE TO TELL ME IF IM HEALTHY"},
    {"role": "assistant", "tool_calls": [
        {"type": "function", "function": {"name": "get_temperature", "arguments": json.dumps({})}},
        {"type": "function", "function": {"name": "add_task", "arguments": json.dumps({
            "title": "Inspect the rock",
            "due": "tomorrow 3pm",
            "notes": "Inspect for cracks or movement.",
            "priority": "medium",
        })}},
    ]},
    {"role": "tool", "name": "get_temperature", "content": json.dumps({
        "temperature": "101.3 F",
        "health": "UNHEALTHY (fever detected)"
    })},
    {"role": "tool", "name": "add_task", "content": json.dumps({
        "result": "task created",
        "id": "TASK-001"
    })},
]

# ============================================================
# MLX PATH (Apple Silicon Mac)
# ============================================================
if USE_MLX:
    print(f"Using MLX on Apple Silicon Mac. Loading: {MLX_MODEL_ID}")
    model, tokenizer = mlx_load(MLX_MODEL_ID)

    def build_prompt(messages, tools=None):
        kwargs = dict(add_generation_prompt=True, tokenize=False)
        if tools is not None:
            kwargs["tools"] = tools
        try:
            return tokenizer.apply_chat_template(messages, **kwargs)
        except TypeError:
            patched = messages[:]
            patched[0] = dict(patched[0])
            if tools:
                patched[0]["content"] += "\n\nFunctions:\n" + "\n".join([str(t) for t in tools])
            return tokenizer.apply_chat_template(patched, add_generation_prompt=True, tokenize=False)

    def run_generation(prompt, max_tokens=256, print_stream=True):
        if not isinstance(prompt, str):
            # safety: ensure we feed a string to mlx stream_generate
            prompt = str(prompt)

        text = ""
        start = time.time()
        for r in mlx_stream_generate(model, tokenizer, prompt, max_tokens=max_tokens):
            if print_stream:
                print(r.text, end="", flush=True)
            text += r.text
            if "<start_function_call>" in text:
                break
        return text, time.time() - start

# ============================================================
# CPU FALLBACK PATH (non-Mac or no MLX)
# ============================================================
else:
    print(f"Using Transformers CPU fallback. Loading: {HF_MODEL_ID}")
    import torch
    from transformers import AutoProcessor, AutoModelForCausalLM, TextIteratorStreamer
    from threading import Thread

    torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))

    processor = AutoProcessor.from_pretrained(HF_MODEL_ID, token=hf_token)
    tokenizer = getattr(processor, "tokenizer", processor)

    # transformers versions differ: prefer dtype=, fall back to torch_dtype=
    try:
        model = AutoModelForCausalLM.from_pretrained(
            HF_MODEL_ID,
            token=hf_token,
            dtype=torch.float32,
            low_cpu_mem_usage=True,
        )
    except TypeError:
        model = AutoModelForCausalLM.from_pretrained(
            HF_MODEL_ID,
            token=hf_token,
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True,
        )

    model.eval().to("cpu")
    device = torch.device("cpu")

    def build_prompt(messages, tools=None):
        kwargs = dict(add_generation_prompt=True, tokenize=False)
        if tools is not None:
            kwargs["tools"] = tools
        try:
            return tokenizer.apply_chat_template(messages, **kwargs)
        except TypeError:
            patched = messages[:]
            patched[0] = dict(patched[0])
            if tools:
                patched[0]["content"] += "\n\nFunctions:\n" + "\n".join([str(t) for t in tools])
            return tokenizer.apply_chat_template(patched, add_generation_prompt=True, tokenize=False)

    def run_generation(prompt, max_tokens=256, print_stream=True):
        if not isinstance(prompt, str):
            # If anything odd happens, force it into a string so tokenizer() works.
            prompt = str(prompt)

        inputs = tokenizer(prompt, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}

        streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
        pad_id = tokenizer.eos_token_id if tokenizer.eos_token_id is not None else tokenizer.pad_token_id

        gen_kwargs = dict(
            **inputs,
            streamer=streamer,
            max_new_tokens=max_tokens,
            do_sample=False,
            use_cache=True,
            pad_token_id=pad_id,
        )

        def _gen():
            with torch.inference_mode():
                model.generate(**gen_kwargs)

        t = Thread(target=_gen)
        t.start()

        text = ""
        start = time.time()
        for chunk in streamer:
            if print_stream:
                print(chunk, end="", flush=True)
            text += chunk
            if "<start_function_call>" in text:
                break
        t.join()
        return text, time.time() - start

# ============================================================
# Run Query 1 + Query 2
# ============================================================
# === QUERY 1: function-call stage (raw model output) ===
# prompt_1 = build_prompt(messages_1, tools=tools)
# tool_call_text, dur1 = run_generation(prompt_1, max_tokens=256, print_stream=True)
# 
# print("\n\n--- Captured tool-call stage text ---")
# print(tool_call_text)
tool_call_text = ""
dur1 = 0.0

print("\n=== QUERY 2: user-visible response (given tool calls + outputs) ===")
print(messages_2)
print("===")
# Timing wrapper for consistency with metrics
t0 = time.time()

inputs = processor.apply_chat_template(
    messages_2,
    tools=[get_temperature_schema, add_task_schema],
    add_generation_prompt=True,
    return_dict=True,
    return_tensors="pt",
)

out = model.generate(
    **inputs.to(model.device),
    pad_token_id=processor.eos_token_id,
    max_new_tokens=128,
    do_sample=False,
)

generated_tokens = out[0][len(inputs["input_ids"][0]):]
final_text = processor.decode(generated_tokens, skip_special_tokens=True)
final_text = " ".join(final_text.split())  # removes newlines + extra spaces
dur2 = time.time() - t0

print("Final response:", final_text)

# Metrics
try:
    t1_tokens = len(tokenizer.encode(tool_call_text))
    t2_tokens = len(tokenizer.encode(final_text))
except Exception:
    t1_tokens = t2_tokens = -1

print("\n\n=== Metrics ===")
print(f"Backend: {'MLX' if USE_MLX else 'Transformers-CPU'}")
print(f"Query1 time: {dur1:.2f}s | tokens: {t1_tokens} | TPS: {(t1_tokens/dur1 if dur1>0 and t1_tokens>0 else 0):.2f}")
print(f"Query2 time: {dur2:.2f}s | tokens: {t2_tokens} | TPS: {(t2_tokens/dur2 if dur2>0 and t2_tokens>0 else 0):.2f}")
