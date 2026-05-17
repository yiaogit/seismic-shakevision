"""Procesamiento de señal (búfer, filtros, detector, espectro).

Los módulos pesados (``filters`` depende de SciPy) se importan a
demanda; este ``__init__`` solo expone las primitivas ligeras del
búfer para no forzar SciPy a quienes solo necesiten almacenamiento.
"""

from shakevision.processing.buffer import BufferSnapshot, RingBuffer

__all__ = ["BufferSnapshot", "RingBuffer"]
