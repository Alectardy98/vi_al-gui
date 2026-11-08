#!/usr/bin/env python3
"""Compile every newly ported IBM Vial target; never flash hardware."""
import argparse,json,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('qmk_root',type=Path)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--jobs',type=int,default=4)
a=p.parse_args();root=a.qmk_root.resolve();a.output.mkdir(parents=True,exist_ok=True)
results=[]
for row in json.loads((root/'keyboards/xwhatsit/vial/ports.json').read_text()):
    start=time.monotonic()
    with (a.output/(row['board']+'.log')).open('w')as log:
        process=subprocess.run(['make',row['target'],'-j'+str(a.jobs)],cwd=root,stdout=log,stderr=subprocess.STDOUT)
    results.append({**row,'returncode':process.returncode,'seconds':round(time.monotonic()-start,2)})
    print(row['target'],process.returncode,flush=True)
(a.output/'builds.json').write_text(json.dumps(results,indent=2)+'\n')
raise SystemExit(any(row['returncode']for row in results))
