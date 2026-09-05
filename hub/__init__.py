"""Job Application Hub.

Two layers, split by the right to call a model (D21):
  - this package is the DETERMINISTIC CORE — queries, rendering, validation.
    It must never call an LLM.
  - agentic work (JD reading, form filling, email classification) happens in a
    Claude Code session, outside this package.
"""

__version__ = "0.1.0"
