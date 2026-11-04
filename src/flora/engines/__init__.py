"""Optional external analysis engines (QIIME 2, DADA2, ALDEx2…) behind one detect/run interface."""

from flora.engines.registry import ENGINES, Engine, detect_all  # noqa: F401
