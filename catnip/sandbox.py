# Copyright 2014 Google Inc. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import fcntl
import logging
import os
import pwd
import random
import signal
import subprocess
import sys
import threading
import time

from catnip import _ext
from catnip import util


SANDBOX_ROOT = '/var/cache/catnip-node'
SANDBOX_CHROOT_DIR = os.path.join(SANDBOX_ROOT, 'chroot')
SANDBOX_HOME_DIR_IN_CHROOT = 'home/catnip-sandbox'
SANDBOX_COMMAND_FILE_IN_CHROOT = 'tmp/catnip-sandbox.command'
SANDBOX_LOCK_BASEDIR = os.path.join(SANDBOX_ROOT, 'lock')
SANDBOX_RUN_BASEDIR = os.path.join(SANDBOX_ROOT, 'run')
SANDBOX_MASTER_LOCK_FILE = os.path.join(SANDBOX_ROOT, 'lock', 'master')
SANDBOX_HEALTH_CHECK_LOCK_FILE = os.path.join(SANDBOX_ROOT,
                                              'lock', 'health-check')
SANDBOX_SETUP_FILE = os.path.join(SANDBOX_ROOT, 'state', 'setup')
SANDBOX_HEALTH_FILE = os.path.join(SANDBOX_ROOT, 'state', 'health')
SANDBOX_USER = 'catnip-sandbox'
SANDBOX_AVAILABLE_PATHS = (
    '/bin', '/etc', '/lib', '/lib32', '/lib64', '/opt', '/sbin', '/usr',
    '/var/lib')
SANDBOX_AVAILABLE_DEVS = (
    'full', 'null', 'random', 'stderr', 'stdin', 'stdout', 'urandom', 'zero')
IPC_CONFIG_FILE = '/usr/lib/catnip-node/ipc.conf'
NEWPID_PATH = '/usr/lib/catnip-node/newpid'
CGROUP_ROOT = '/sys/fs/cgroup'
CGROUP_SUBSYSTEMS = ('cpuacct', 'cpuset', 'memory')
CATNIP_SANDBOX_INIT_PATH = '/usr/lib/catnip-node/catnip-sandbox-init'

_LOG_FORMATTER = logging.Formatter(
    fmt='%(levelname)s %(asctime)-15s [%(filename)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')


class InternalError(Exception):
  pass


class SandboxParams(util.ValidatedStruct):
  cpu = util.ValidatedProperty(type=int, validator=util.RangeValidator(0, 255))
  share_cpu = util.ValidatedProperty(type=bool, default=False)
  block = util.ValidatedProperty(type=bool, default=True)
  disk_limit_kb = util.ValidatedProperty(
      type=int, validator=util.RangeValidator(64, 4*1024*1024))
  ignore_health = util.ValidatedProperty(type=bool, default=False)
  debug = util.ValidatedProperty(type=bool, default=False)


class RunRequest(util.ValidatedStruct):
  time_limit_sec = util.ValidatedProperty(
      type=float, validator=util.RangeValidator(0, 24*60*60))
  cpu_time_limit_sec = util.ValidatedProperty(
      type=float, validator=util.RangeValidator(0, 24*60*60))
  memory_limit_kb = util.ValidatedProperty(
      type=int, validator=util.RangeValidator(0, 4*1024*1024))
  output_limit_kb = util.ValidatedProperty(
      type=int, validator=util.RangeValidator(0, 4*1024*1024))
  command = util.ValidatedProperty(type=str)


class RunResponse(object):
  def __init__(self, status, output_file):
    self._status = status
    self._output_file = output_file

  status = property(lambda self: self._status)
  output_file = property(lambda self: self._output_file)


class SandboxMaster(object):
  def __init__(self):
    pass

  def Open(self, params, disk_image_stream):
    return Sandbox(params, disk_image_stream)

  def GetStatus(self):
    with util.Lock(SANDBOX_MASTER_LOCK_FILE, fcntl.LOCK_SH):
      status = {}
      status['status'] = self._GetMasterStatus()
      status['sandbox'] = []
      try:
        for sandbox_id in xrange(256):
          status['sandbox'].append(self._GetSandboxStatus(sandbox_id))
      except KeyError:
        pass
    return status

  def _GetMasterStatus(self):
    if not os.path.exists(SANDBOX_SETUP_FILE):
      return 'shutdown'
    try:
      with util.Lock(
          SANDBOX_HEALTH_CHECK_LOCK_FILE, fcntl.LOCK_SH|fcntl.LOCK_NB):
        with open(SANDBOX_HEALTH_FILE) as f:
          return f.readline().strip()
    except util.LockFailed:
      return 'warmup'
    except IOError:
      return 'warmup'

  def _GetSandboxStatus(self, sandbox_id):
    # Throws KeyError when the user does not exist.
    pwd.getpwnam('catnip%d' % sandbox_id)
    try:
      with util.Lock(os.path.join(SANDBOX_LOCK_BASEDIR, '%d' % sandbox_id),
                     fcntl.LOCK_SH|fcntl.LOCK_NB):
        pass
    except util.LockFailed:
      return {'status': 'running'}
    else:
      return {'status': 'ready'}


class Sandbox(object):
  def __init__(self, params, disk_image_stream):
    assert isinstance(params, SandboxParams)
    if not params.Validate():
      raise InternalError('Invalid SandboxParams')
    self._params = params
    self._sandbox_mount_id = 'catnip-sandbox%d' % params.cpu
    self._sandbox_lock_file = os.path.join(
        SANDBOX_LOCK_BASEDIR, '%d' % params.cpu)
    self._sandbox_output_file = os.path.join(
        SANDBOX_RUN_BASEDIR, '%d.output' % params.cpu)
    self._cgroup_id = self._GenerateRandomID()
    self._cgroup_dir = os.path.join(
          CGROUP_ROOT, 'cpuset', self._cgroup_id)
    self._cgroup_dirs = {}
    for subsystem in CGROUP_SUBSYSTEMS:
      self._cgroup_dirs[subsystem] = os.path.join(
          CGROUP_ROOT, subsystem, self._cgroup_id)
    self._log = logging.getLogger('catnip.sandbox')
    if not self._params.debug:
      self._log.setLevel(logging.CRITICAL)
    else:
      self._log.setLevel(logging.INFO)
      log_handler = logging.StreamHandler(sys.stderr)
      log_handler.setFormatter(_LOG_FORMATTER)
      self._log.addHandler(log_handler)
    self._context = self._Context(disk_image_stream)
    self._context.next()

  ##############################################################################
  ##  Setup

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_value, exc_tb):
    self.Close()
    return False

  def Close(self):
    if self._context:
      try:
        self._context.next()
      except StopIteration:
        pass
      self._context = None

  def _Context(self, disk_image_stream):
    self._SetCpuAffinity(self._params.cpu)
    with self._ConnectionWatcher():
      with self._EnvironmentSwap():
        with self._SandboxLock():
          self._Unshare()
          self._ConfigureIpc()
          self._UnmountAll()
          self._SetupChroot()
          self._InitializeDisk(disk_image_stream)
          yield

  def _SetCpuAffinity(self, cpu):
    if isinstance(cpu, int):
      cpu = [cpu]
    cpu = ','.join(map(str, cpu))
    if 0 != self._RunSilently(['taskset', '-cp', cpu, str(os.getpid())]):
      raise InternalError('Invalid CPU specification')

  def _ConnectionWatcher(self):
    @contextlib.contextmanager
    def Watcher():
      self._log.info('starting connection watcher...')
      lead_pid = self._FindLeadProcess()
      self._log.info('lead_pid: %s', lead_pid)
      if not lead_pid:
        return
      cancelled = False
      def WatchThread():
        while self._GetParentPID(lead_pid) > 1 and not cancelled:
          time.sleep(0.5)
        while not cancelled:
          self._KillallCgroup()
          time.sleep(0.5)
      watcher = threading.Thread(target=WatchThread)
      watcher.daemon = True
      watcher.start()
      self._log.info('connection watcher started.')
      yield
      cancelled = True
      self._log.info('connection watcher stopped.')
    return Watcher()

  def _FindLeadProcess(self):
    sudo_pid = os.getpgid(0)
    self._log.info('sudo_pid: %d', sudo_pid)
    ssh_pid = self._GetParentPID(sudo_pid)
    self._log.info('ssh_pid: %d', ssh_pid)
    if not ssh_pid:
      raise InternalError('Could not find the lead process')
    try:
      with open('/proc/%d/cmdline' % ssh_pid) as f:
        ssh_cmdline = f.read()
    except IOError:
      raise InternalError('Could not find the lead process')
    self._log.info('ssh_cmdline: %s', ssh_cmdline)
    if not ssh_cmdline.startswith('sshd: '):
      if self._params.debug:
        self._log.info('skipping SSH invocation check by --debug')
        return None
      raise InternalError('Not invoked from SSH')
    return sudo_pid

  def _EnvironmentSwap(self):
    @contextlib.contextmanager
    def Swapper():
      self._log.info('setting umask/PATH')
      last_umask = os.umask(022)
      last_path = os.environ['PATH']
      os.environ['PATH'] = '/usr/sbin:/usr/bin:/sbin:/bin'
      yield
      self._log.info('recovering umask/PATH')
      os.environ['PATH'] = last_path
      os.umask(last_umask)
    return Swapper()

  def _SandboxLock(self):
    @contextlib.contextmanager
    def Locker():
      self._log.info('locking sandbox %d', self._params.cpu)
      with util.Lock(SANDBOX_MASTER_LOCK_FILE, fcntl.LOCK_SH):
        if not os.path.exists(SANDBOX_SETUP_FILE):
          raise InternalError('Sandbox is not ready')
        if not self._params.ignore_health:
          try:
            with util.Lock(
                SANDBOX_HEALTH_CHECK_LOCK_FILE, fcntl.LOCK_SH|fcntl.LOCK_NB):
              with open(SANDBOX_HEALTH_FILE) as f:
                health = (f.readline().strip() == 'healthy')
          except util.LockFailed:
            # A health checker is running.
            health = None
          except IOError:
            # No health checker has run yet.
            health = None
          if health is None:
            raise InternalError('Sandbox is not ready')
          if health is False:
            raise InternalError('Sandbox is unhealthy')
        lock_mode = fcntl.LOCK_SH if self._params.share_cpu else fcntl.LOCK_EX
        if not self._params.block:
          lock_mode |= fcntl.LOCK_NB
        try:
          with util.Lock(self._sandbox_lock_file, lock_mode):
            self._log.info('locked sandbox %d', self._params.cpu)
            yield
            self._log.info('unlocking sandbox %d', self._params.cpu)
        except util.LockFailed:
          raise InternalError('Sandbox is locked')
      self._log.info('unlocked sandbox %d', self._params.cpu)
    return Locker()

  def _Unshare(self):
    self._log.info('unsharing...')
    _ext.unshare(_ext.CLONE_NEWIPC|_ext.CLONE_NEWNET|_ext.CLONE_NEWNS|
                 _ext.CLONE_NEWUTS)

  def _ConfigureIpc(self):
    if 0 != self._RunSilently(['sysctl', '-p', IPC_CONFIG_FILE]):
      raise InternalError('Failed to configure IPC')

  def _UnmountAll(self):
    self._log.info('unmounting filesystems...')
    paths = []
    path_whitelist = tuple(
        ['/', '/dev', '/proc', '/sys', CGROUP_ROOT] +
        [os.path.join(CGROUP_ROOT, subsystem)
         for subsystem in CGROUP_SUBSYSTEMS])
    with open('/proc/mounts') as f:
      for line in f:
        path = line.split()[1]
        if path not in path_whitelist:
          paths.append(path)
    paths.sort(key=lambda p: len(p), reverse=True)
    for path in paths:
      self._LazyUnmount(path)

  def _SetupChroot(self):
    self._log.info('setting up chroot...')
    # Create /
    self._Mount(
        'tmpfs',
        'nosuid,nodev,size=%dk,uid=0,gid=0,mode=755' % (
            self._params.disk_limit_kb),
        'none',
        SANDBOX_CHROOT_DIR)
    # Create /dev
    os.mkdir(os.path.join(SANDBOX_CHROOT_DIR, 'dev'))
    self._Mount(
        'tmpfs',
        'nosuid,size=64k,uid=0,gid=0,mode=755',
        'none',
        os.path.join(SANDBOX_CHROOT_DIR, 'dev'))
    for dev in SANDBOX_AVAILABLE_DEVS:
      oldpath = os.path.join('/dev', dev)
      newpath = os.path.join(SANDBOX_CHROOT_DIR, 'dev', dev)
      if os.path.islink(oldpath):
        linkpath = os.readlink(oldpath)
        os.symlink(linkpath, newpath)
      else:
        with open(newpath, 'w'):
          pass
        self._BindMount(oldpath, newpath)
    # Mount other available paths
    for path in SANDBOX_AVAILABLE_PATHS:
      if not os.path.isdir(path):
        continue
      path = path.strip('/')
      os.makedirs(os.path.join(SANDBOX_CHROOT_DIR, path))
      self._BindMount(
          os.path.join('/', path), os.path.join(SANDBOX_CHROOT_DIR, path),
          options='nosuid,nodev,ro')
    # Create /tmp, /var/tmp
    os.mkdir(os.path.join(SANDBOX_CHROOT_DIR, 'tmp'))
    self._RunSilently(
        ['chmod', '1777', os.path.join(SANDBOX_CHROOT_DIR, 'tmp')])
    os.symlink(os.path.join(os.pardir, 'tmp'),
               os.path.join(SANDBOX_CHROOT_DIR, 'var', 'tmp'))
    # Create /proc placeholder - mounted after CLONE_NEWPID
    os.mkdir(os.path.join(SANDBOX_CHROOT_DIR, 'proc'))
    # Create /home/catnip-sandbox
    os.makedirs(os.path.join(SANDBOX_CHROOT_DIR, SANDBOX_HOME_DIR_IN_CHROOT))
    self._RunSilently(
        ['chown', 'catnip-sandbox.',
         os.path.join(SANDBOX_CHROOT_DIR, SANDBOX_HOME_DIR_IN_CHROOT)])

  def _InitializeDisk(self, disk_image_stream):
    tar_shell_command = (
        'cd /%(sandbox_home)s; '
        'exec sudo -u %(sandbox_user)s tar --no-overwrite-dir -x') % {
        'sandbox_home': SANDBOX_HOME_DIR_IN_CHROOT,
        'sandbox_user': SANDBOX_USER,
        }
    if self._params.debug:
      tar_shell_command += ' -v'
    args = ['chroot', SANDBOX_CHROOT_DIR, NEWPID_PATH,
            'bash', '-c', tar_shell_command]
    self._log.info('extracting tarball: %s', ' '.join(args))
    try:
      with open(os.devnull, 'w') as null:
        out = sys.stderr if self._params.debug else null
        returncode = subprocess.call(args,
                                     close_fds=True,
                                     stdin=disk_image_stream,
                                     stdout=out,
                                     stderr=out)
        self._log.info('return code: %d', returncode)
        if returncode != 0:
          raise InternalError('Tar command failed')
    except OSError:
      raise InternalError('Failed to run tar')

  ##############################################################################
  ##  Execution

  def Execute(self, request):
    assert isinstance(request, RunRequest)
    if not request.Validate():
      raise InternalError('Invalid RunRequest')
    with self._Cgroup(request):
      main_proc, limiter_proc, start_time = self._SpawnProgram(request)
      killer = None
      end_time = None
      try:
        killer = self._MaybeLaunchTimeoutKiller(main_proc, start_time, request)
        self._log.info('waiting for the main program to finish...')
        main_proc.wait()
        end_time = time.time()
        self._log.info('program finished.')
      finally:
        if killer:
          killer.Cancel()
        self._KillallCgroup()
        self._log.info('waiting for the limiter to finish...')
        limiter_proc.wait()
      if end_time is None:
        runtime = None
      else:
        runtime = end_time - start_time
      self._log.info('success.')
      return self._BuildResponse(request, main_proc.returncode, runtime)

  def _Cgroup(self, request):
    @contextlib.contextmanager
    def Cgroup():
      self._log.info('setting up cgroup...')
      for subsystem, cgroup_dir in self._cgroup_dirs.iteritems():
        try:
          os.mkdir(cgroup_dir, 0700)
        except OSError:
          raise InternalError('Failed to create a cgroup: %s' % subsystem)
      try:
        self._SetCgroupParam('cpuset.cpus', self._params.cpu)
        self._SetCgroupParam('cpuset.mems', 0)
        if request.memory_limit_kb > 0:
          self._SetCgroupParam('memory.limit_in_bytes',
                               request.memory_limit_kb * 1024)
      except IOError:
        raise InternalError('Failed to set up a cgroup')
      yield
      for subsystem, cgroup_dir in self._cgroup_dirs.iteritems():
        try:
          os.rmdir(cgroup_dir)
        except OSError:
          pass
    return Cgroup()

  def _SetCgroupParam(self, name, value):
    self._log.info('%s = %s', name, value)
    subsystem = name.split('.')[0]
    with open(os.path.join(self._cgroup_dirs[subsystem], name), 'w') as f:
      print >>f, value

  def _SpawnProgram(self, request):
    try:
      with open(os.path.join(SANDBOX_CHROOT_DIR,
                             SANDBOX_COMMAND_FILE_IN_CHROOT), 'w') as f:
        print >>f, '#!/bin/bash'
        print >>f, request.command
        os.fchmod(f.fileno(), 0755)
    except IOError:
      raise InternalError('Failed to prepare command')
    except OSError:
      raise InternalError('Failed to prepare command')
    self._log.info('command line: %s', request.command)
    main_shell_command = (
        'for cgroup_dir in %(cgroup_dirs)s; do '
        'echo $$ > $cgroup_dir/tasks; done;'
        'echo -1000 > /proc/self/oom_score_adj;'
        'chroot %(chroot_dir)s '
        '%(newpid_path)s '
        '%(catnip_sandbox_init_path)s') % {
        'cgroup_dirs': ' '.join(self._cgroup_dirs.values()),
        'chroot_dir': SANDBOX_CHROOT_DIR,
        'newpid_path': NEWPID_PATH,
        'catnip_sandbox_init_path': CATNIP_SANDBOX_INIT_PATH,
        }
    if request.output_limit_kb > 0:
      limiter_args = ['head', '-c', '%dK' % request.output_limit_kb]
    else:
      limiter_args = ['cat']
    try:
      os.unlink(self._sandbox_output_file)
    except OSError:
      pass
    try:
      with open(os.devnull, 'w') as null:
        with open(self._sandbox_output_file, 'w') as out:
          try:
            self._log.info('invoking limiter: %s', ' '.join(limiter_args))
            limiter_proc = subprocess.Popen(
                limiter_args, close_fds=True, stdin=subprocess.PIPE, stdout=out,
                stderr=null)
          except OSError:
            raise InternalError('Failed to run limiter')
          start_time = time.time()
          try:
            self._log.info('invoking main program: %s', main_shell_command)
            main_proc = subprocess.Popen(
                [main_shell_command], shell=True, close_fds=True, stdin=null,
                stdout=limiter_proc.stdin, stderr=null)
          except OSError:
            self._log.info('oops, main program invocation failed.')
            limiter_proc.kill()
            limiter_proc.wait()
            raise InternalError('Failed to run the main program')
          finally:
            limiter_proc.stdin.close()
          self._log.info('spawned the main program')
          return (main_proc, limiter_proc, start_time)
    except IOError:
      raise InternalError('Failed to open the output file')

  def _MaybeLaunchTimeoutKiller(self, proc, start_time, request):
    if request.time_limit_sec == 0 and request.cpu_time_limit_sec == 0:
      self._log.info('timeout killer suppressed')
      return None
    if request.time_limit_sec > 0:
      time_limit_deadline = start_time + request.time_limit_sec
    else:
      time_limit_deadline = 0
    killer = TimeoutKiller(
        proc, time_limit_deadline, request.cpu_time_limit_sec,
        os.path.join(self._cgroup_dirs['cpuacct'], 'cpuacct.usage'))
    killer.daemon = True
    killer.start()
    self._log.info('started timeout killer')
    return killer

  def _BuildResponse(self, request, returncode, runtime):
    if returncode < 0:
      returncode = 128 - returncode
    try:
      with open(os.path.join(
          self._cgroup_dirs['cpuacct'], 'cpuacct.usage')) as f:
        cpu_usage = float(f.read().strip()) / 1e9
    except IOError:
      raise InternalError('Failed to read cpuacct.usage')
    try:
      with open(os.path.join(
          self._cgroup_dirs['memory'], 'memory.max_usage_in_bytes')) as f:
        memory_usage = int(f.read().strip()) / 1024
    except IOError:
      raise InternalError('Failed to read memory.max_usage_in_bytes')
    try:
      output_length = os.stat(self._sandbox_output_file).st_size
    except OSError:
      output_length = 0
    status = {
        'returncode': returncode,
        'time': runtime,
        'cputime': cpu_usage,
        'memory': memory_usage,
        'length': output_length,
        'command': request.command,
        }
    return RunResponse(status, self._sandbox_output_file)

  ##############################################################################
  ##  Utilities

  def _KillallCgroup(self):
    self._log.info('killing all cgroup processes...')
    while True:
      try:
        with open(os.path.join(self._cgroup_dir, 'tasks')) as f:
          pids = map(int, f.read().split())
        if not pids:
          break
        for pid in pids:
          try:
            os.kill(pid, signal.SIGKILL)
          except OSError:
            pass
        self._log.info('killed %s', ', '.join(map(str, pids)))
      except IOError:
        pass

  def _Mount(self, fstype, options, oldpath, newpath):
    returncode = self._RunSilently(
        ['mount', '-n', '-t', fstype, '-o', options, oldpath, newpath])
    if returncode != 0:
      raise InternalError('Failed to mount: %s' % newpath)

  def _LazyUnmount(self, path):
    returncode = self._RunSilently(['umount', '-n', '-l', path])
    if returncode != 0:
      raise InternalError('Failed to unmount: %s' % path)

  def _BindMount(self, oldpath, newpath, options=''):
    returncode = self._RunSilently(
        ['mount', '-n', '--bind', oldpath, newpath])
    if returncode != 0:
      raise InternalError('Failed to bind mount: %s' % newpath)
    returncode = self._RunSilently(
        ['mount', '-n', '-o', 'remount,bind,%s' % options, oldpath, newpath])
    if returncode != 0:
      raise InternalError('Failed to bind mount: %s' % newpath)

  def _RunSilently(self, args):
    self._log.info('running silently: %s', ' '.join(args))
    try:
      with open(os.devnull, 'w') as null:
        out = sys.stderr if self._params.debug else null
        return subprocess.call(args, close_fds=True,
                               stdin=null, stdout=out, stderr=out)
    except OSError:
      raise InternalError('Failed to run %s' % args[0])

  def _GetParentPID(self, pid):
    try:
      with open('/proc/%d/stat' % pid) as f:
        line = f.read().strip()
      info = line.rsplit(') ', 1)[-1].split()
      return int(info[1])
    except:
      return None

  def _GenerateRandomID(self):
    return ''.join([random.choice('0123456789abcdef') for _ in xrange(32)])


class TimeoutKiller(threading.Thread):
  def __init__(self, proc, time_limit_deadline, cpu_time_limit,
               cpuacct_usage_path):
    super(TimeoutKiller, self).__init__()
    self._proc = proc
    self._time_limit_deadline = time_limit_deadline
    self._cpu_time_limit = cpu_time_limit
    self._cpuacct_usage_path = cpuacct_usage_path
    self._running = True

  def run(self):
    with open(os.path.join(self._cpuacct_usage_path)) as cpuacct_usage:
      while self._running:
        cpuacct_usage.seek(0)
        if ((self._time_limit_deadline > 0 and
             time.time() > self._time_limit_deadline) or
            (self._cpu_time_limit > 0 and
             float(cpuacct_usage.read()) / 1e9 > self._cpu_time_limit)):
          try:
            self._proc.kill()
          except OSError:
            pass
          break
        time.sleep(0.1)

  def Cancel(self):
    self._running = False
