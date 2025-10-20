import sys, pathlib
# add repo root so "import app" works regardless of where pytest runs from
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
