#!/usr/bin/env python3
"""Compare KLE geometry against QMK source, including real shape overlaps."""
from pathlib import Path
import argparse,json,sys,math
p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
# Run from a source checkout so this uses the app's own KLE decoder.
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'src/main/python'))
from kle_serial import Serial
cases=json.loads((a.output/'cases.json').read_text());report=[]
for case in cases:
 keys=Serial().deserialize(case['definition']['layouts']['keymap']).keys
 got={tuple(map(int,k.labels[0].split(','))):k for k in keys};expected=case['qmk_layouts'][case['layout']]['layout']
 differences=[]
 for key in expected:
  actual=got[tuple(key['matrix'])]
  for source,name,default in [('x','x',0),('y','y',0),('w','width',1),('h','height',1),('x2','x2',0),('y2','y2',0),('w2','width2',key.get('w',1)),('h2','height2',key.get('h',1))]:
   if not math.isclose(key.get(source,default),getattr(actual,name),abs_tol=1e-7):differences.append([key['matrix'],source,key.get(source,default),getattr(actual,name)])
 overlaps=[]
 for i,k in enumerate(keys):
  for other in keys[i+1:]:
   dx=min(k.x+k.width,other.x+other.width)-max(k.x,other.x);dy=min(k.y+k.height,other.y+other.height)-max(k.y,other.y)
   if dx>1e-6 and dy>1e-6:overlaps.append([k.labels[0],other.labels[0],round(dx*dy,3)])
 variants={name:len(item['layout'])for name,item in case['qmk_layouts'].items()}
 report.append({'board':case['board'],'geometry_differences':differences,'overlaps':overlaps,'current_source_layout':case['layout'],'current_keys':len(keys),'compiled_base_layout':case['keymap_layout'],'compiled_base_layout_keys':variants[case['keymap_layout']],'source_variants':variants})
(a.output/'geometry-results.json').write_text(json.dumps(report,indent=2)+'\n')
print('Geometry mismatches:',sum(bool(r['geometry_differences'])for r in report),'layouts; overlapping rectangles:',sum(bool(r['overlaps'])for r in report),'layouts')
for r in report:
 if r['overlaps']or r['current_keys']!=r['compiled_base_layout_keys']:print(r['board'],r['current_keys'],'vs base',r['compiled_base_layout_keys'],'overlaps',len(r['overlaps']))
