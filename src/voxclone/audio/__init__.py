"""Audio processing package marker.

Architectural Rule:
Modules in voxclone.audio must remain strictly torch-free.
They are utilized by multiprocessing pool workers on CPU.
"""
