"""
The merged model into Ollama, 4-bit, under a name of its own:

    python to_ollama.py --name shishya-code-trained

Three steps, because this Ollama compresses only some architectures itself:
llama.cpp's converter turns the merged weights into an F16 GGUF, its
llama-quantize makes the Q4_K_M copy (the same compression as the model it
replaces), and `ollama create` imports that with shishya-code's own prompt
template and settings (out/Modelfile, written by merge.py).

Needs llama.cpp beside this folder: the converter from its repository
(llama.cpp/convert_hf_to_gguf.py, with gguf-py installed) and llama-quantize.exe
from one of its Windows releases in tools/llama/.
"""

import argparse
import hashlib
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
OLLAMA = Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"


def settled(path, wait=120):
    """The quantizer reports done before Windows has finished writing the
    file; importing then fails with "changed during create". Wait until two
    reads agree."""
    last = None
    for _ in range(wait // 5):
        h = hashlib.sha256(path.read_bytes()[:1 << 24] + str(path.stat().st_mtime).encode()).hexdigest()
        if h == last:
            return
        last = h
        time.sleep(5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="shishya-code-trained")
    args = ap.parse_args()
    f16, q4 = OUT / f"{args.name}-f16.gguf", OUT / f"{args.name}-q4_K_M.gguf"
    subprocess.run([sys.executable, str(ROOT / "llama.cpp" / "convert_hf_to_gguf.py"), str(OUT / "merged"),
                    "--outfile", str(f16), "--outtype", "f16"], check=True)
    subprocess.run([str(ROOT / "tools" / "llama" / "llama-quantize.exe"), str(f16), str(q4), "Q4_K_M"], check=True)
    settled(q4)
    modelfile = OUT / "Modelfile"
    lines = modelfile.read_text(encoding="utf-8").split("\n", 1)
    modelfile.write_text(f"FROM {q4}\n{lines[1] if len(lines) > 1 else ''}", encoding="utf-8")
    subprocess.run([str(OLLAMA), "create", args.name, "-f", str(modelfile)], check=True)
    print(f"{args.name} is in Ollama. Compare it before giving it the code job: compare.py")


if __name__ == "__main__":
    main()
