"""Machine learning worker for keep-one-voice.

The worker is driven by the TypeScript CLI over stdio using newline delimited
JSON. Keep heavy imports (torch, demucs, pyannote) inside the stage functions
that need them so that starting the worker stays cheap and the protocol layer
stays testable without the model stack installed.
"""

__version__ = "0.0.0"
