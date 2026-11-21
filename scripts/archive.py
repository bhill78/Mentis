"""Freeze delivery manifest, then archive and verify every delivered byte.

python scripts/archive.py --manifest
git add . && git commit ...
python scripts/archive.py --zip
"""
from pathlib import Path
import hashlib,json,sys,zipfile,subprocess
R=Path(__file__).resolve().parents[1]
def paths():
 return sorted(p for p in R.rglob('*') if p.is_file() and '.git' not in p.relative_to(R).parts and '__pycache__' not in p.parts and p.suffix!='.zip' and p.name!='delivery-manifest.json')
def digest(b):return hashlib.sha256(b).hexdigest()
if '--manifest' in sys.argv:
 files={p.relative_to(R).as_posix():{'sha256':digest(p.read_bytes()),'bytes':p.stat().st_size} for p in paths()}
 (R/'delivery-manifest.json').write_text(json.dumps({'purpose':'Exact final Gen 3 design delivery bytes; self excluded','files':files},indent=2),encoding='utf-8')
 print('Manifest prepared:',len(files),'files')
if '--zip' in sys.argv:
 m=json.loads((R/'delivery-manifest.json').read_text())
 for path,entry in m['files'].items():
  assert digest((R/path).read_bytes())==entry['sha256'],path
 revision=subprocess.check_output(['git','-C',str(R),'rev-parse','HEAD'],text=True).strip()
 archive=R/'magnet-ui-gen3-review-bundle.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
  for path in m['files']:z.write(R/path,'magnet-ui-gen3/'+path)
  z.write(R/'delivery-manifest.json','magnet-ui-gen3/delivery-manifest.json')
  z.writestr('magnet-ui-gen3/BUILD_REVISION.txt',revision+'\nBranch: quiet-magnet-gen3\nStatic design artifacts only; no deployment.\n')
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  for path,entry in m['files'].items():assert digest(z.read('magnet-ui-gen3/'+path))==entry['sha256'],path
 print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'sha256':digest(archive.read_bytes()),'verifiedFileHashes':len(m['files']),'crcErrors':0,'commit':revision}))
