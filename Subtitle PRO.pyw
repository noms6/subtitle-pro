"""Double-click launcher: .pyw files run with pythonw, so no console window appears."""
import os
import runpy
import sys

here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)
sys.path.insert(0, here)
sys.argv = [os.path.join(here, "translate_srt.py")]
runpy.run_path(sys.argv[0], run_name="__main__")
