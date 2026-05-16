"""Fuse an ONNX model with external weights into a single-file ONNX.

Usage:
    uv run python scripts/fuse_wakeword_onnx.py <input.onnx> [<output.onnx>]

If output is omitted, the input is replaced in place (the original is moved to
<input>.external_backup.onnx and the corresponding .onnx.data file is left
alone for cleanup).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import onnx
from onnx.external_data_helper import load_external_data_for_model


def fuse(input_path: Path, output_path: Path) -> None:
    model = onnx.load(str(input_path), load_external_data=False)
    load_external_data_for_model(model, str(input_path.parent))
    # Save without external_data flag = embed all weights as raw initializers
    onnx.save(model, str(output_path))


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    input_path = Path(sys.argv[1]).resolve()
    if not input_path.exists():
        sys.exit(f"input not found: {input_path}")
    output_path = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else input_path

    if output_path == input_path:
        backup = input_path.with_suffix(".external_backup.onnx")
        shutil.copy2(input_path, backup)
        print(f"backed up original to: {backup}")

    fuse(input_path, output_path)
    size_mb = output_path.stat().st_size / 1_048_576
    print(f"wrote fused single-file ONNX: {output_path} ({size_mb:.2f} MB)")
    data_file = input_path.with_suffix(".onnx.data")
    if data_file.exists():
        print(f"note: {data_file} is no longer needed and can be deleted")


if __name__ == "__main__":
    main()
