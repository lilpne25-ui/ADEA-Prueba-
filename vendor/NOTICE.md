# Third-party code

## rapidocr_onnxruntime 1.2.3
- Source: https://github.com/RapidAI/RapidOCR (PyPI: rapidocr_onnxruntime)
- License: Apache License 2.0 (https://www.apache.org/licenses/LICENSE-2.0)
- Why vendored: the PyPI package depends on opencv-python (GUI build, needs libGL). Vercel's Python
  runtime cannot install system libraries, so the package is shipped unmodified here and its
  dependencies are installed explicitly with opencv-python-headless instead (see requirements.txt).
- Includes the PP-OCR ONNX models distributed with the package (Apache-2.0, PaddleOCR).
