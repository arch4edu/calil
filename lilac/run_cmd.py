import logging
import os
import subprocess
import sys
import signal

logger = logging.getLogger(__name__)

def run_cmd(cmd, *, use_pty=False, silent=False, env=None, cwd=None):
  logger.debug('running %r, %susing pty,%s showing output', cmd,
               '' if use_pty else 'not ',
               ' not' if silent else '')
  if use_pty:
    rfd, stdout = os.openpty()
    stdin = stdout
    # for fd leakage debugging
    logger.debug('pty master fd=%d, slave fd=%d.', rfd, stdout)
  else:
    stdin = subprocess.DEVNULL
    stdout = subprocess.PIPE

  exited = False
  def child_exited(signum, sigframe): # pylint: disable=unused-argument
    nonlocal exited
    exited = True
  old_hdl = signal.signal(signal.SIGCHLD, child_exited)

  p = subprocess.Popen(
    cmd,
    env = env,
    cwd = cwd,
    stdin = stdin, stdout = stdout, stderr = subprocess.STDOUT,
  )
  if use_pty:
    os.close(stdout)
  else:
    rfd = p.stdout.fileno()
  out = []

  while True:
    try:
      r = os.read(rfd, 4096)
      if not r:
        if exited:
          break
        else:
          continue
    except InterruptedError:
      continue
    except OSError as e:
      if e.errno == 5: # Input/output error: no clients run
        break
      else:
        raise
    r = r.replace(b'\x0f', b'') # ^O
    if not silent:
      sys.stderr.buffer.write(r)
    out.append(r)

  code = p.wait()
  if use_pty:
    os.close(rfd)
  if old_hdl is not None:
    signal.signal(signal.SIGCHLD, old_hdl)

  out = b''.join(out)
  out = out.decode('utf-8', errors='replace')
  if code != 0:
    raise subprocess.CalledProcessError(code, cmd, out)
  return out

