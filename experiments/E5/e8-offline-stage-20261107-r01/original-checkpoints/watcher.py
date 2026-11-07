
import ctypes,json,os,pathlib,select,struct
P=pathlib.Path("/inspire/hdd/project/26-the-other-shore/263140062/physics_discovery")
A=P/"deployment/e8-checkpoint-archive-075ee3c"
S=P/"deployment/e8-source-075ee3c/deployment/sr-work"
lib=ctypes.CDLL(None,use_errno=True);fd=lib.inotify_init1(0);watches={}
def watch(path):
 wd=lib.inotify_add_watch(fd,os.fsencode(path),0x100|0x80|0x8)
 if wd>=0:watches[wd]=path
for jobs in S.glob("shore-sr-*/jobs"):
 watch(jobs)
 for d in jobs.iterdir():
  if d.is_dir():watch(d)
(A/"ready.json").write_text(json.dumps({"watch_directories":[str(x) for x in watches.values()]}))
while True:
 select.select([fd],[],[],1)
 data=os.read(fd,65536);offset=0
 while offset<len(data):
  wd,mask,cookie,length=struct.unpack_from("iIII",data,offset);offset+=16
  name=data[offset:offset+length].split(b"\0")[0].decode();offset+=length
  base=watches.get(wd)
  if base is None:continue
  target=base/name
  if mask&0x40000000:
   if target.is_dir():watch(target)
   continue
  if name not in ("request.json","progress.json","result.json"):continue
  try:
   raw=target.read_bytes();value=json.loads(raw)
   dest=A/base.name;dest.mkdir(exist_ok=True)
   filename=dest/name;temporary=filename.with_suffix(".tmp");temporary.write_bytes(raw);temporary.replace(filename)
   print(json.dumps({"job":base.name,"file":name,"bytes":len(raw),"axes":{k:len(v) for k,v in value.get("axis_equations",{}).items()}}),flush=True)
  except (OSError,ValueError):pass
