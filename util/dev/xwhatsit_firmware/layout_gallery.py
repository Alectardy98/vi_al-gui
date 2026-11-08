#!/usr/bin/env python3
"""Create a local visual review gallery and photo/contact-sheet artifacts."""
import argparse,json,html,math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps
p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();root=a.output
cases=json.loads((root/'cases.json').read_text());photos={r['board']:r for r in json.loads((root/'photo-results.json').read_text())};font=ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans.ttf',20)if Path('/usr/share/fonts/TTF/DejaVuSans.ttf').exists()else ImageFont.load_default()
# Photo contacts are reference presentation only; original downloaded files stay unchanged.
for group in range(4):
 subset=cases[group*6:group*6+6]
 if not subset:continue
 sheet=Image.new('RGB',(1600,math.ceil(len(subset)/2)*430),'#211c28');draw=ImageDraw.Draw(sheet)
 for i,case in enumerate(subset):
  x=(i%2)*800;y=(i//2)*430;draw.text((x+12,y+8),case['board'],font=font,fill='white')
  photo=photos.get(case['board'],{});file=root/photo.get('file','missing')
  try:
   im=Image.open(file).convert('RGB')
   if im.width<200:raise ValueError('Source photo is missing/placeholder')
   im.thumbnail((775,380));sheet.paste(im,(x+(800-im.width)//2,y+43+(380-im.height)//2))
  except Exception as error:draw.text((x+12,y+120),str(error)[:70],font=font,fill='#ffb4b4')
 sheet.save(root/f'photos-{group+1}.png')
print('Photo contact sheets generated; run again after captures for the complete gallery.')
# Keyboard-only contact sheets use actual Qt widget screenshots, not a redraw.
for group in range(4):
 subset=cases[group*6:group*6+6]
 if not subset:continue
 sheet=Image.new('RGB',(1800,math.ceil(len(subset)/2)*370),'#211c28');draw=ImageDraw.Draw(sheet)
 for i,case in enumerate(subset):
  x=(i%2)*900;y=(i//2)*370
  draw.text((x+12,y+8),case['board']+' · '+str(len(case['qmk_layouts'][case['layout']]['layout']))+' positions',font=font,fill='white')
  im=Image.open(root/(case['board']+'-keyboard.png')).convert('RGB');im.thumbnail((875,310))
  sheet.paste(im,(x+(900-im.width)//2,y+43+(310-im.height)//2))
 sheet.save(root/f'vial-layouts-{group+1}.png')
geometry={r['board']:r for r in json.loads((root/'geometry-results.json').read_text())}
# Independent source diagrams: direct QMK x/y/w/h rectangles and matrix IDs.
for case in cases:
 for name,item in case['qmk_layouts'].items():
  keys=item['layout'];left=min(k['x']for k in keys);top=min(k['y']for k in keys);right=max(k['x']+k.get('w',1)for k in keys);bottom=max(k['y']+k.get('h',1)for k in keys);scale=58
  image=Image.new('RGB',(round((right-left)*scale)+28,round((bottom-top)*scale)+28),'#211c28');draw=ImageDraw.Draw(image)
  for key in keys:
   x=(key['x']-left)*scale+14;y=(key['y']-top)*scale+14;w=key.get('w',1)*scale-4;h=key.get('h',1)*scale-4
   draw.rounded_rectangle((x,y,x+w,y+h),radius=4,fill='#41374d',outline='#8a739e',width=1)
   label='%d,%d'%tuple(key['matrix']);box=draw.textbbox((0,0),label,font=font)
   draw.text((x+(w-(box[2]-box[0]))/2,y+(h-(box[3]-box[1]))/2-4),label,font=font,fill='white')
  image.save(root/(case['board']+'-'+name+'.png'))

intro='''<!doctype html><html><head><meta charset="utf-8"><title>IBM Vial layout visual review</title><style>
body{background:#19151f;color:#eee9f4;font:16px/1.55 system-ui;margin:0 auto;padding:30px;max-width:1550px}h1,h2,h3{color:#d6b5ff}a{color:#cea6ff}section{border:1px solid #55445f;padding:22px;margin:28px 0;border-radius:9px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:22px}.columns>div{min-width:0}img{width:100%;object-fit:contain;max-height:520px;background:#211c28}table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #55445f;text-align:left}.warning{color:#ffcf83}.muted{color:#bbb0c5}code{color:#cfb2ec}details{margin:12px 0} @media(max-width:900px){.columns{grid-template-columns:1fr}}
</style></head><body><h1>IBM Vial layouts — visual audit</h1>
<p>All 22 new JSONs were loaded through Vi_al 1.0.10’s built-in offline JSON loader, with HID access disabled. These are actual desktop Qt screenshots, with legends read from each compiled firmware’s base keymap. Your connected keyboards and EEPROM were not accessed.</p>
<p><strong>Result:</strong> all 22 load; no lost matrix positions, geometry mismatches against the selected QMK layout, or overlapping key rectangles were found. That does <em>not</em> mean every current image represents a stock assembled keyboard.</p>
<p class="warning">Nine boards have multiple source layouts, but their generated JSON currently shows the all-switch-position layout with no physical-layout selector. Six contain more displayed positions than their compiled base-layout macro. The clearest example is the 4978: 171 positions displayed versus the 122-key base layout. A physical-layout choice/default is still needed before calling these stock-accurate.</p>
<p>Reference photos come from the original firmware READMEs in Git, except F107’s dead Imgur image, replaced by a Model F Labs product reference. Photos show particular specimens or PCBs, sometimes modified. Key labels are our QMK assignments, not original IBM printed legends. The independent diagrams below use the source QMK geometry directly; they are not produced by the Vial JSON converter.</p>
<p>The bundled app’s offline dummy loader also exposed an unrelated MY-2K add-on assumption (<code>DummyKeyboard.amk_rgb_strip</code> missing). The successful audit therefore used the core build of the same Vi_al version. Normal connected-device operation was not tested or changed here.</p>
<h2>Board summary</h2><table><tr><th>Board</th><th>Current positions</th><th>Compiled base-layout positions</th><th>Review result</th></tr>'''
parts=[intro]
for case in cases:
 board=case['board'];g=geometry[board];multiple=len(case['qmk_layouts'])>1
 status='Physical-layout variants need selection'if multiple else 'Matches single source geometry; compare specimen photo'
 if board in('test','test2'):status='Bench grid, not a physical keyboard drawing'
 elif board=='beamal_badpinout':status='Experimental pinout; specimen not verified'
 parts.append(f'<tr><td><a href="#{board}">{board}</a></td><td>{g["current_keys"]}</td><td>{g["compiled_base_layout_keys"]}</td><td>{status}</td></tr>')
parts.append('</table>')
for case in cases:
 board=case['board'];g=geometry[board];photo=photos.get(board,{})
 parts.append(f'<section id="{board}"><h2>{html.escape(case["definition"]["name"])} · {board}</h2><p>Selected source: <code>{case["layout"]}</code> · {g["current_keys"]} positions. Compiled base macro: <code>{case["keymap_layout"]}</code> · {g["compiled_base_layout_keys"]} positions.</p>')
 parts.append('<div class="columns"><div><h3>Reference photo / PCB</h3>')
 if photo.get('image_valid'):
  parts.append(f'<a href="{html.escape(photo["file"],quote=True)}"><img src="{html.escape(photo["file"],quote=True)}"></a><p class="muted"><a href="{html.escape(photo.get("source_page",photo.get("url","")),quote=True)}">Original image/source</a></p>')
 else:parts.append('<p>Usable source image unavailable.</p>')
 parts.append(f'</div><div><h3>Actual Vi_al offline-loaded layout</h3><a href="{board}-keyboard.png"><img src="{board}-keyboard.png"></a><p><a href="{board}-vial.png">Full Vi_al screenshot</a></p></div></div>')
 if board in('test','test2','beamal_badpinout'):parts.append('<p class="warning">Experimental/test target. Its inherited source picture is not proof that this definition represents that assembled keyboard.</p>')
 elif len(case['qmk_layouts'])>1:parts.append('<p class="warning">The JSON currently exposes all switch positions. Named physical alternatives below exist in QMK source but are not yet selectable in this generated Vial definition.</p>')
 parts.append('<details><summary>Independent QMK layout diagrams and matrix positions</summary>')
 for name,item in case['qmk_layouts'].items():parts.append(f'<h3>{name} · {len(item["layout"])} positions</h3><a href="{board}-{name}.png"><img src="{board}-{name}.png"></a>')
 parts.append('</details></section>')
parts.append('<p>Audit only: no firmware source, Vial JSON, EEPROM or attached device was modified. Photographs and independent source diagrams cannot verify electrical matrix wiring. Newly ported physical boards still need switch-by-switch acceptance.</p></body></html>')
(root/'index.html').write_text(''.join(parts))
print(root/'index.html')
