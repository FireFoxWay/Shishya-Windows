"""
LoRA fine-tune of Qwen2.5-Coder-7B-Instruct on the verified examples, in
4-bit so it fits a 16 GB graphics card. Only the answer (the script) is
learned; the system prompt and the request are context.

    python train_lora.py --epochs 2
"""

import argparse
import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "base" / "qwen2.5-coder-7b-instruct"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--data", default=str(ROOT / "work" / "train.jsonl"))
    ap.add_argument("--max-steps", type=int, default=-1, help="a short smoke test")
    ap.add_argument("--out", default=str(ROOT / "out"))
    args = ap.parse_args()
    out = Path(args.out)

    rows = [json.loads(l) for l in Path(args.data).read_text(encoding="utf-8").splitlines()]
    data = Dataset.from_list(rows)
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForCausalLM.from_pretrained(
        BASE, device_map={"": 0}, dtype=torch.bfloat16,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                               bnb_4bit_compute_dtype=torch.bfloat16,
                                               bnb_4bit_use_double_quant=True))
    lora = LoraConfig(r=args.rank, lora_alpha=args.rank * 2, lora_dropout=0.05, task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                      "gate_proj", "up_proj", "down_proj"])
    cfg = SFTConfig(output_dir=str(out / "lora"), num_train_epochs=args.epochs, max_steps=args.max_steps,
                    per_device_train_batch_size=1, gradient_accumulation_steps=8,
                    learning_rate=args.lr, lr_scheduler_type="cosine", warmup_steps=5,
                    logging_steps=5, save_strategy="epoch", bf16=True, max_length=3072,
                    gradient_checkpointing=True, completion_only_loss=True, report_to=[])
    trainer = SFTTrainer(model=model, args=cfg, train_dataset=data, processing_class=tok, peft_config=lora)
    trainer.train()
    trainer.save_model(str(out / "adapter"))
    print("saved adapter to", out / "adapter")


if __name__ == "__main__":
    main()
