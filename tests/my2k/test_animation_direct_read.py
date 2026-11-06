from pathlib import Path
import sys,unittest,struct
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/main/python'))
from vi_al_addons.my2k.animation_fast_transport import FastAnimationTransport
class DirectReadNegotiation(unittest.TestCase):
 def test_two_sided_capability_required_and_framing_preserved(self):
  class Interface(list):bInterfaceClass=255;bInterfaceSubClass=0xaf;bInterfaceProtocol=3;bInterfaceNumber=3
  for aux,main in [(0,0),(128,0),(0,1),(128,1)]:
   with self.subTest(aux=aux,main=main):
    class Device:
     def __init__(self):self.q=b'';self.events=[]
     def get_active_configuration(self):return [Interface([SimpleNamespace(bEndpointAddress=5,bmAttributes=2,wMaxPacketSize=512),SimpleNamespace(bEndpointAddress=133,bmAttributes=2,wMaxPacketSize=512)])]
     def ctrl_transfer(self,kind,request,value,index,data,timeout):
      if request==0x62:return b'AFB\0'
      if kind==0x40:self.q=bytes(data);return len(data)
      r=bytearray(32);r[:7]=bytes((253,238,170,2,0,self.q[4],2));r[12:17]=b'AFB7\x0a';r[20:22]=struct.pack('<H',4096);r[22]=aux;r[23]=main;return r
     def write(self,ep,data,timeout):self.q=bytes(data);self.events.append(('out',len(data)));return len(data)
     def read(self,ep,n,timeout):
      self.events.append(('in',n));r=bytearray(n);r[:7]=bytes((253,238,170,2,2,self.q[4],2));r[30:32]=struct.pack('<H',n-32);return r
    device=Device()
    with patch('usb.util.claim_interface'),patch('usb.util.release_interface'):
     fast=FastAnimationTransport(None,device);fast.capabilities(1);want=4096 if aux and main else 4064;self.assertEqual(fast.read_size,want);fast.request(2,2,2,0,bytes(want));self.assertEqual(device.events,[('out',32),('in',32+want)]);fast.close()
if __name__=='__main__':unittest.main()
