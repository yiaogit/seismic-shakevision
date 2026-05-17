"""
Capa de servicios externos.

Agrupa los clientes HTTP que consumen feeds públicos de:

  * **USGS** (sismos recientes a nivel mundial)
  * **Raspberry Shake / FDSN** (catálogo de estaciones de la red AM)

y la infraestructura común de caché en disco para que las llamadas a
red sean ocasionales y la UI siempre tenga algo que mostrar (incluso
sin conexión, si hay caché reciente).

Los módulos no dependen de Qt: cualquier fetch es síncrono y se puede
testear con fixtures locales. La integración con la UI se hace a
través de ``services.worker.DataRefreshWorker`` (QObject + QThread).
"""

from shakevision.services.cache import FileCache
from shakevision.services.data_models import Earthquake, PagerLevel, ShakeStation

__all__ = ["Earthquake", "FileCache", "PagerLevel", "ShakeStation"]

# Los clientes IRIS/ShakeNet/USGS se importan a demanda para evitar
# arrastrar urllib cuando solo se necesitan los modelos.
