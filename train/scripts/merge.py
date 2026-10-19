"""
Fold the trained adapter into the base weights (bf16, on the CPU — 32 GB of
RAM holds a 7B model) and write a folder Ollama can import:

    python merge.py
    ollama create shishya-code-trained -f out/Modelfile --quantize q4_K_M
"""

import subprocess
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "base" / "qwen2.5-coder-7b-instruct"
OUT = ROOT / "out" / "merged"
OLLAMA = Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"

model = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16, device_map={"": "cpu"})
model = PeftModel.from_pretrained(model, ROOT / "out" / "adapter").merge_and_unload()
model.save_pretrained(OUT, safe_serialization=True)
AutoTokenizer.from_pretrained(BASE).save_pretrained(OUT)

# The same prompt template, system prompt and settings as shishya-code, so the
# only difference measured is the training.
shown = subprocess.run([str(OLLAMA), "show", "shishya-code", "--modelfile"], capture_output=True,
                       text=True, encoding="utf-8").stdout
keep = [l for l in shown.splitlines() if not l.startswith(("FROM ", "#"))]
(ROOT / "out" / "Modelfile").write_text(f"FROM {OUT}\n" + "\n".join(keep) + "\n", encoding="utf-8")
print("merged into", OUT)
