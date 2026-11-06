"""Keep the local frontend SSH forward connected; Ctrl-C stops the tunnel."""
import subprocess
import time

command = ['ssh', '-N', '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=30',
           '-o', 'ServerAliveCountMax=3', '-o', 'ConnectTimeout=15',
           '-L', '127.0.0.1:8765:127.0.0.1:8765', 'qz-infer']
while True:
    process = subprocess.Popen(command)
    try:
        code = process.wait()
        print('SSH forward disconnected; reconnecting', code, flush=True)
        time.sleep(3)
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        break
