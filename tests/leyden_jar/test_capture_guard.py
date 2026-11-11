"""Exercise only the guard predicate; never import or wrap real HID."""
import ast
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
source=ast.parse((ROOT/'util/dev/hid_read_guard.py').read_text())
namespace={'allowed_amk':set()}
exec(compile(ast.Module(body=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='allowed'],type_ignores=[]),'guard-predicate','exec'),namespace)
allowed=namespace['allowed']
def packet(op,command):return bytes([0,op,command,0xc0,0x21])+bytes(28)
@pytest.mark.parametrize('command',[0x81,0x82,0x83,0x85,0x86,0x8c,0x8d,0x8e,0x8f,0x90,0x91,0x92,0x93,0x95])
def test_native_reads(command):assert allowed(packet(2,command))
@pytest.mark.parametrize('command',[0x84,0x87,0x88])
def test_native_snapshots(command):assert allowed(packet(3,command))
@pytest.mark.parametrize('command',[0x83,0x85,0x89,0x8a,0x8b,0x93,0x94,0x96])
def test_native_mutations_rejected(command):assert not allowed(packet(3,command))
