"""Server-to-server SSH streaming. Local credentials never leave this computer."""
import json
import queue
import shlex
import subprocess
import threading
import time

# The source server uses its own SSH credentials and known_hosts. The target file
# is an exclusively-created staging file owned by the mapping worker.
SINK = r'''
import json, os, sys
p=json.loads(sys.argv[1])
fd=os.open(p['target'],os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW)
count=0
with os.fdopen(fd,'wb') as out:
    while True:
        chunk=sys.stdin.buffer.read(1024*1024)
        if not chunk: break
        out.write(chunk)
        count+=len(chunk)
if count!=p['size']: raise RuntimeError('文件大小校验失败')
'''

SOURCE = r'''
import json, os, shlex, subprocess, sys, threading, time
p=json.loads(sys.stdin.readline())
command=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
         '-o','ConnectTimeout=8','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2',
         '-p',str(p['port']),'-l',p['user'],p['host'],
         'python3 -c '+shlex.quote(p['sink'])+' '+shlex.quote(json.dumps(p))]
child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
count=0
failure=[]
errors=[]
def read_errors():
    while True:
        data=child.stderr.read(1024)
        if not data: break
        errors.append(data.decode('utf-8',errors='replace'))
        del errors[:-4]
def control():
    sys.stdin.read()
    if child.poll() is None: child.kill()
def watch():
    previous=0
    started=time.monotonic()
    while child.poll() is None:
        time.sleep(1)
        print(json.dumps({'progress':count}),flush=True)
        elapsed=time.monotonic()-started
        if elapsed>=15:
            if (count-previous)/elapsed < p['minimum_mbps']*1024*1024:
                failure.append('直传连续15秒低于设定速度，切换本机中转')
                child.kill()
                return
            previous=count
            started=time.monotonic()
for function in (read_errors,control,watch):
    threading.Thread(target=function,daemon=True).start()
try:
    fd=os.open(p['source'],os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as reader:
        while True:
            chunk=reader.read(1024*1024)
            if not chunk: break
            child.stdin.write(chunk)
            child.stdin.flush()
            count+=len(chunk)
    child.stdin.close()
    code=child.wait()
    if code or count!=p['size']:
        raise RuntimeError(''.join(failure or errors) or '直传未完成或源文件发生变化')
    print(json.dumps({'done':True}),flush=True)
except Exception as exc:
    if child.poll() is None: child.kill()
    child.wait()
    print(json.dumps({'error':''.join(failure) or str(exc)+' '+''.join(errors)}),flush=True)
finally:
    if child.poll() is None: child.kill()
    child.wait()
'''


def direct_copy(source, target, path, staging, size, stopped, minimum_mbps=1, progress=None):
    args=target.args
    payload=dict(source=path,target=staging,size=size,host=args[-1],
                 user=args[args.index('-l')+1],port=int(args[args.index('-p')+1]),
                 minimum_mbps=max(0.01,minimum_mbps),sink=SINK)
    command='python3 -u -c '+shlex.quote(SOURCE)
    process=(source.session.open_process(command) if source.session else
             subprocess.Popen(source.args+[command],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
    lines=queue.Queue()
    def read():
        try:
            for line in process.stdout: lines.put(line)
        finally:
            lines.put(None)
    threading.Thread(target=read,daemon=True).start()
    try:
        process.stdin.write(json.dumps(payload)+'\n')
        process.stdin.flush()
        last=time.monotonic()
        errors=[]
        while True:
            if stopped.is_set(): raise RuntimeError('映射已取消')
            if time.monotonic()-last>25: raise TimeoutError('服务器直传握手或响应超时')
            try: line=lines.get(timeout=0.1)
            except queue.Empty: continue
            if line is None: raise RuntimeError('直传连接失败：'+''.join(errors)[-500:])
            try: event=json.loads(line)
            except ValueError:
                errors.append(line)
                errors=errors[-4:]
                continue
            last=time.monotonic()
            if event.get('error'): raise RuntimeError(event['error'])
            if progress and 'progress' in event:
                progress(event['progress'])
            if event.get('done'): return
    finally:
        # EOF tells the remote controller to kill its child SSH process.
        try:
            if source.session: process.channel.shutdown_write()
            process.stdin.close()
        finally:
            deadline=time.monotonic()+3
            while process.poll() is None and time.monotonic()<deadline:
                time.sleep(0.05)
            if process.poll() is None: process.kill()
            if not source.session: process.wait(timeout=5)
            process.stdout.close()
