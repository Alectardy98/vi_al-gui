"""Port recognition uses immutable identities plus the real Vial matrix."""
import json
from pathlib import Path
from types import SimpleNamespace
from vi_al_addons.xwhatsit import protocol


def test_all_ibm_ports_are_recognized_without_probing_unknown_devices():
    profiles=json.loads(Path(protocol.__file__).with_name('profiles.json').read_text())
    assert len(profiles)==29
    assert len({p['uid']for p in profiles[7:]})==22
    for p in profiles:
        keyboard=SimpleNamespace(keyboard_id=int.from_bytes(bytes.fromhex(p['uid']),'little'),rows=p['rows'],cols=p['cols'])
        assert protocol.supported(keyboard)
        keyboard.rows=32
        assert not protocol.supported(keyboard)
