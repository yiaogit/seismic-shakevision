"""Tests para ``shakevision.ui.signal_safety.subscribe`` (v0.7.7, B1).

No requieren un ``QApplication``: usamos una señal/owner falsos que
emulan el contrato mínimo (``connect`` / ``disconnect`` / ``destroyed`` /
``emit``). Así el comportamiento — adaptación de aridad, guardia de
``RuntimeError`` y auto-desconexión en ``destroyed`` — se verifica sin
depender de un backend Qt gráfico.
"""

from __future__ import annotations

import pytest

from shakevision.ui.signal_safety import _max_positional, subscribe


# ----------------------------------------------------------------------
# Dobles de prueba
# ----------------------------------------------------------------------
class FakeSignal:
    """Señal mínima: lista de slots + emit que respeta el orden."""

    def __init__(self) -> None:
        self._slots: list = []

    def connect(self, slot) -> None:
        self._slots.append(slot)

    def disconnect(self, slot) -> None:
        if slot in self._slots:
            self._slots.remove(slot)
        else:
            raise TypeError("slot no conectado")

    def emit(self, *args) -> None:
        for slot in list(self._slots):
            slot(*args)


class FakeOwner:
    """Owner mínimo: expone ``destroyed`` como otra FakeSignal."""

    def __init__(self) -> None:
        self.destroyed = FakeSignal()


# ----------------------------------------------------------------------
# _max_positional
# ----------------------------------------------------------------------
def test_max_positional_counts_params():
    assert _max_positional(lambda: None) == 0
    assert _max_positional(lambda a: None) == 1
    assert _max_positional(lambda a, b: None) == 2
    assert _max_positional(lambda *a: None) is None  # *args = ilimitado


def test_max_positional_excludes_self_on_bound_method():
    class C:
        def zero(self):
            ...

        def one(self, x):
            ...

    c = C()
    assert _max_positional(c.zero) == 0
    assert _max_positional(c.one) == 1


# ----------------------------------------------------------------------
# subscribe: adaptación de aridad
# ----------------------------------------------------------------------
def test_subscribe_truncates_extra_args_like_qt():
    sig, owner = FakeSignal(), FakeOwner()
    seen = []

    def zero_arg():           # como `_retranslate(self)` sin parámetros
        seen.append("z")

    def one_arg(value):       # como `_on_theme_changed(self, theme)`
        seen.append(("o", value))

    subscribe(owner, sig, zero_arg)
    subscribe(owner, sig, one_arg)
    sig.emit("payload")       # la señal emite 1 arg

    assert seen == ["z", ("o", "payload")]


# ----------------------------------------------------------------------
# subscribe: guardia de RuntimeError (objeto C++ muerto)
# ----------------------------------------------------------------------
def test_subscribe_swallows_runtimeerror():
    sig, owner = FakeSignal(), FakeOwner()

    def dead_cpp(*_a):
        raise RuntimeError("Internal C++ object already deleted")

    subscribe(owner, sig, dead_cpp)
    # No debe propagar — si propagara, esto lanzaría.
    sig.emit("x")


# ----------------------------------------------------------------------
# subscribe: auto-desconexión en destroyed
# ----------------------------------------------------------------------
def test_subscribe_disconnects_on_destroyed():
    sig, owner = FakeSignal(), FakeOwner()
    hits = []
    subscribe(owner, sig, lambda *_a: hits.append(1))

    assert len(sig._slots) == 1
    owner.destroyed.emit()           # el widget se destruye
    assert len(sig._slots) == 0      # ya no estamos suscritos
    sig.emit("y")
    assert hits == []                # no se vuelve a llamar


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
