#!/usr/bin/env python3
"""Export protocol vectors from the original Python codecs; no hardware access."""
import base64,json,lzma,struct,sys,zlib
from io import BytesIO
from PIL import Image
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
for addon in ('ec_42','my2k','alienware_aw768'):
    sys.path.insert(0,str(ROOT/'addons'/addon/'python'))
from vi_al_addons.my2k.touch_bar_protocol import encode as touch_encode
from vi_al_addons.my2k.sleep_mode_protocol import encode as sleep_encode
from vi_al_addons.my2k.oled_config import encode_config
from vi_al_addons.my2k.lock_lights2_protocol import encode_rules
from vi_al_addons.ec_42.protocol import PROFILES,be16,decode_record,encode,Op
from vi_al_addons.my2k.animation_rle import encode_python
from vi_al_addons.my2k.oled_typing_preview import ASCII_GLYPHS,typing_bitmap
fixed=[dict(enabled=True,color=(i*30,255-i*20,100),effect=i,speed=i+3)for i in range(5)]
locks=dict(rules=[dict(trigger=1,enabled=True,layer=0,effect=2,speed=7,color=(255,0,0)),dict(trigger=4,enabled=True,layer=3,effect=3,speed=4,color=(0,255,0))],fallback_enabled=True,fallback=(1,2,3),fixed=fixed)
touch=dict(mode=1,sensitivity=67,left=170,right=169,tap=168,tap_jitter=42)
sleep=dict(enabled=True,minutes=15)
oled=dict(message='Hello Vi_al',label='MY2K',typing=True,happy=False,clock=True,font_family='DejaVu Sans Mono',font_size=8,bitmap=None)
p=PROFILES[0]
record=bytearray(bytes([0])+be16(550)+be16(500)+be16(550)+bytes([70,70])+be16(0xc384)*p.cells)
meta=len(record);record+=be16(p.magic)+be16(0x42)+bytes(4)+bytes(p.cells)
native=bytearray(record)
for i in list(range(1,7,2))+list(range(9,meta+8,2)):native[i],native[i+1]=native[i+1],native[i]
crc=zlib.crc32(native);record[meta+4:meta+8]=be16(crc&65535)+be16(crc>>16)
decode_record(record,p)
definition={'name':'MY-2K browser test fixture','matrix':{'rows':3,'cols':5},'inputPerformance':{'version':1},'lighting':'none','keyboardType':'mx_state','layouts':{'labels':[['Enter','Normal','Split']], 'keymap':[['0,0','0,1','0,2','0,3','0,4'],[{'w':1.5},'1,0',{'w':1},'1,1','1,2','1,3'],[{'w':2},'2,0',{'w':1},'2,1','2,2','2,3']]},'customKeycodes':[{'name':'MY2K_STORAGE_TOGGLE','shortName':'Storage','title':'Storage mode'}],'amkFeature':[{'rgb_strip':{'effects':['Disabled','Static','Rainbow'],'strips':[{'name':'Top left'},{'name':'LED Square'}]},'rgb_grid':{'effects':['Disabled','Static'],'grids':[{'name':'Right Grid'}]}}]}
fixture=dict(touch=dict(values=touch,raw=touch_encode(**touch).hex()),sleep=dict(values=sleep,raw=sleep_encode(**sleep).hex()),oled=dict(values=oled,raw=encode_config(**oled).hex()),locks=dict(values=locks,raw=encode_rules(**locks).hex()),ec=dict(record=bytes(record).hex(),request=encode(Op.SET_ACTUATION,123,be16(4)+bytes([37])+be16(9)).hex()),definition=definition,compressed=base64.b64encode(lzma.compress(json.dumps(definition).encode())).decode(),rle=[dict(raw=raw.hex(),encoded=encode_python(raw).hex())for raw in (bytes(4096),bytes(range(256))*16,b'\x12\x34'*128+b'\x01\x02\x03\x04'*64)])
ec_definition=json.loads(json.dumps(definition))
ec_definition.update(name='EC42 browser test fixture', matrix={'rows':6,'cols':16})
ec_definition.pop('inputPerformance');ec_definition.pop('amkFeature')
fixture.update(ecDefinition=ec_definition,ecCompressed=base64.b64encode(lzma.compress(json.dumps(ec_definition).encode())).decode())
aw_definition=json.loads(json.dumps(ec_definition))
aw_definition.update(name='Alienware AW768 browser test fixture',matrix={'rows':3,'cols':5})
fixture.update(awCompressed=base64.b64encode(lzma.compress(json.dumps(aw_definition).encode())).decode())
core_definition=json.loads(json.dumps(aw_definition))
core_definition['name']='Generic Vial browser test fixture'
fixture.update(coreCompressed=base64.b64encode(lzma.compress(json.dumps(core_definition).encode())).decode())
gif=BytesIO()
Image.new('RGB',(4,2),'red').save(gif,format='GIF',save_all=True,append_images=[Image.new('RGB',(4,2),'blue')],duration=[50,100],loop=0)
fixture['gif']=base64.b64encode(gif.getvalue()).decode()
fixture['typing']={'label':'MY2K','bitmap':typing_bitmap('MY2K').hex()}
(ROOT/'web/src/data/typing-glyphs.json').write_text(json.dumps(list(ASCII_GLYPHS))+'\n')
(ROOT/'web/tests/fixtures/protocols.json').write_text(json.dumps(fixture,indent=2)+'\n')
(ROOT/'web/src/data/cp437.json').write_text(json.dumps(bytes(range(256)).decode('cp437'),ensure_ascii=False)+'\n')
print('Exported Python protocol vectors and compressed test definition')
