"""Composition-layer service wiring.

This package now holds only the ``ServiceContainer`` (`container.py`), which
composes Tier 1 engine services (``lorecraft.engine.services``) with the Tier 2
feature services (``lorecraft.features.<feature>.service``). It is deliberately
*not* in ``engine/`` — the container imports features, which the engine may not.
"""
