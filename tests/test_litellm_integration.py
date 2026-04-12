from __future__ import annotations

import sys
from types import SimpleNamespace

from epi_recorder.integrations.litellm import EPICallback, disable_epi, enable_epi


def test_enable_epi_uses_primary_litellm_callbacks(monkeypatch):
    fake_litellm = SimpleNamespace(callbacks=[])
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    callback = enable_epi()
    enable_epi()

    assert isinstance(callback, EPICallback)
    assert len([cb for cb in fake_litellm.callbacks if isinstance(cb, EPICallback)]) == 1

    disable_epi()

    assert fake_litellm.callbacks == []


def test_enable_epi_falls_back_to_success_failure_callbacks(monkeypatch):
    fake_litellm = SimpleNamespace(success_callback=["existing"], failure_callback=[])
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    callback = enable_epi()

    assert fake_litellm.success_callback == ["existing", callback]
    assert fake_litellm.failure_callback == [callback]
