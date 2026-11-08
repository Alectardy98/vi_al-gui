#!/usr/bin/env python3
"""Fetch only the source READMEs' reference photographs into the review folder."""
from pathlib import Path
import json,urllib.request,concurrent.futures,argparse,io
from PIL import Image
p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();rows=json.loads((a.output/'cases.json').read_text())
def fetch(row):
 if not row['photo_urls']:return {'board':row['board'],'status':'no source photograph'}
 url=row['photo_urls'][0];result={'board':row['board'],'url':url}
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
  with urllib.request.urlopen(req,timeout=20)as r:
   data=r.read(10*1024*1024+1)
  if len(data)>10*1024*1024:raise ValueError('reference photo exceeds 10 MiB')
  image=Image.open(io.BytesIO(data));image.verify()
  extension={'JPEG':'.jpg','PNG':'.png','WEBP':'.webp'}.get(image.format,'.image')
  file=a.output/(row['board']+'-photo'+extension);file.write_bytes(data)
  result.update(status='Downloaded; visual reference still needs specimen review.',file=file.name,image_valid=image.width>=200)
  if image.width<200:result['status']='Small image/placeholder; do not treat as a keyboard photo.'
 except Exception as error:result['status']=str(error)
 return result
with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:results=list(pool.map(fetch,rows))
(a.output/'photo-results.json').write_text(json.dumps(results,indent=2)+'\n')
print('Downloaded',sum('file'in r for r in results),'of',len(rows),'source reference photos.')
