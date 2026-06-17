import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
# Allow tests to import shared helpers (e.g., _stub_claude)
sys.path.insert(0, os.path.dirname(__file__))
