# Training Shishya's code model

Fine-tunes the model behind the **Code** app (and chat's "work it out" step) on
your own kind of files, on your own graphics card. Nothing leaves the machine.

It works by **learning from verified successes**:

1. **Tasks with known answers.** `make_tasks.py` writes folders of realistic
   files (sales logs, stock sheets with title rows, marks, expenses) and
   requests like *"how many products need reordering in stock.xlsx"*, each with
   the answer computed from the data, never by a model.
2. **Candidate scripts.** `sample.py` asks a model through Ollama exactly as the
   Code app does (same system prompt, same file listing).
3. **Checked in the sandbox.** `verify.vbs` runs every script inside Shishya's
   sandbox, with that task's folder as home, and keeps it only if it exits
   cleanly and prints the known answer.
4. **Fine-tune.** `build_sft.py` builds the training set, holding whole folders
   out for the test. `train_lora.py` trains a 4-bit LoRA on
   Qwen2.5-Coder-7B-Instruct.
5. **Into Ollama.** `merge.py` folds the LoRA into the model, and
   `to_ollama.py` converts it, compresses it to Q4_K_M and imports it.
6. **Compare before you switch.** `compare.py` has the old and new model
   answer the held-out tasks, which neither trained on, then reports the score
   after the sandbox checks it.

On an RTX 5080 laptop (16 GB) the first run took about 3 hours, mostly
sampling. The training itself took 16 minutes.

## Result of the first run

118 held-out tasks in 27 folders the model never saw:

| Code model | Correct |
|---|---|
| `shishya-code` (tuned prompts only) | 19% |
| `shishya-code` + the missing-import repair now in Shishya | 59% |
| `shishya-code-trained` (this pipeline) | **74%** |

## Run it

**Close Shishya's apps while it runs.** Sampling and the apps share one Ollama,
and Ollama has no priority, so a report would wait behind hundreds of requests.

```
cd train
python -m venv venv
venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cu128
venv\Scripts\python -m pip install -r requirements.txt
venv\Scripts\python -c "from huggingface_hub import snapshot_download as d; d('Qwen/Qwen2.5-Coder-7B-Instruct', local_dir='base/qwen2.5-coder-7b-instruct')"
```

Shishya's own Python (it has pandas and Shishya's code) makes the tasks and the
samples:

```
set PY=%LOCALAPPDATA%\Programs\Shishya\runtime\python.exe
%PY% scripts\make_tasks.py --n 180
%PY% scripts\sample.py --model shishya-code --k 2
explorer verify.vbs                 (wait for work\verify.done)
%PY% scripts\sample.py --model shishya-code --k 3 --temperature 0.9 --only-failed --tag b
explorer verify.vbs
%PY% scripts\build_sft.py
venv\Scripts\python scripts\train_lora.py --epochs 2
venv\Scripts\python scripts\merge.py
venv\Scripts\python scripts\to_ollama.py --name shishya-code-trained
%PY% scripts\compare.py sample shishya-code shishya-code-trained
explorer verify.vbs
%PY% scripts\compare.py report
```

`to_ollama.py` needs llama.cpp beside these scripts. That means the repository
(for `convert_hf_to_gguf.py`, with `pip install ./llama.cpp/gguf-py`) and
`llama-quantize.exe` from one of its Windows releases, in `tools/llama/`.

If the new model scores better, give it the code job on the clone's Models
screen.
