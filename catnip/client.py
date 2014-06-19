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

import os
import signal
import subprocess
import sys

from catnip import protocol
from catnip import sandbox


class ClientError(Exception):
  pass


class CatnipClient(object):
  def __init__(self):
    self._hostname = None
    self._port = 22
    self._username = 'catnip'
    self._identity_file = None
    self._disk_image_stream = None
    self._check_ssh_host_key = False
    self._multiplex = False
    self._debug = False

  ##############################################################################
  ##  Setters

  def SetHost(self, hostname, port=22):
    if not isinstance(hostname, str):
      raise TypeError('hostname must be a string')
    if not (isinstance(port, int) and 1 <= port < 65536):
      raise TypeError('invalid port')
    self._hostname = hostname
    self._port = port

  def SetUser(self, username):
    if not isinstance(username, str):
      raise TypeError('username must be a string')
    self._username = username

  def SetIdentityFile(self, identity_file):
    self._identity_file = identity_file

  def SetDiskImageStream(self, disk_image_stream):
    if not hasattr(disk_image_stream, 'read'):
      raise TypeError('disk_image_stream must be a stream')
    self._disk_image_stream = disk_image_stream

  def SetCheckSSHHostKey(self, check_ssh_host_key):
    if not isinstance(check_ssh_host_key, bool):
      raise TypeError('check_ssh_host_key must be a boolean')
    self._check_ssh_host_key = check_ssh_host_key

  def SetMultiplex(self, multiplex):
    if not isinstance(multiplex, bool):
      raise TypeError('multiplex must be a boolean')
    self._multiplex = multiplex

  def SetDebug(self, debug):
    if not isinstance(debug, bool):
      raise TypeError('debug must be a boolean')
    self._debug = debug

  ##############################################################################
  ##  Actions

  def Run(self, params, requests, extra_files,
          output_filename=None, callback=None):
    if ((not output_filename and not callback) or
        (output_filename and callback)):
      raise ValueError('One of output_filename or callback should be passed.')
    if not params.Validate():
      raise ValueError('Insufficient SandboxParams')
    for request in requests:
      if not request.Validate():
        raise ValueError('Insufficient RunRequest')
    self._CheckSettingsBeforeRun()
    args = self._BuildSSHArgs() + self._BuildRunArgs()
    if params.debug:
      print >>sys.stderr, ' '.join(args)
    proc = None
    try:
      with open(os.devnull, 'w') as null:
        stderr = None if self._debug else null
        if output_filename:
          with open(output_filename, 'w') as stdout:
            proc = subprocess.Popen(args,
                                    close_fds=True,
                                    stdin=subprocess.PIPE,
                                    stdout=stdout,
                                    stderr=stderr)
        else:
          proc = subprocess.Popen(args,
                                  close_fds=True,
                                  stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  stderr=stderr)
      writer = protocol.RequestWriter(proc.stdin)
      writer.WriteParams(params)
      for request in requests:
        writer.WriteRunRequest(request)
      for extra_file in extra_files:
        writer.WriteExtraFile(os.path.basename(extra_file), extra_file)
      if self._disk_image_stream:
        writer.WriteDiskImage(self._disk_image_stream)
      writer.Finish()
      proc.stdin.close()
      if callback:
        reader = protocol.ResponseReader(proc.stdout)
        reader.Read(callback)
      proc.wait()
      if proc.returncode != 0:
        raise ClientError('Failed to start a remote program')
      proc = None
    except KeyboardInterrupt:
      if params.debug:
        print >>sys.stderr, 'Interrupted during execution.'
    finally:
      if proc and proc.poll() is None:
        os.kill(proc.pid, signal.SIGINT)

  def GetStatus(self):
    self._CheckSettingsBeforeRun()
    args = self._BuildSSHArgs() + self._BuildGetStatusArgs()
    with open(os.devnull, 'w') as null:
      stderr = None if self._debug else null
      proc = subprocess.Popen(args,
                              close_fds=True,
                              stdin=null,
                              stdout=subprocess.PIPE,
                              stderr=stderr)
    status = proc.communicate(None)[0]
    if proc.returncode != 0:
      raise ClientError('Failed to start a remote program')
    return status

  def EndMultiplex(self):
    self._CheckSettingsBeforeRun()
    args = self._BuildSSHArgs() + self._BuildEndMultiplexArgs()
    with open(os.devnull, 'w') as null:
      stderr = None if self._debug else null
      proc = subprocess.Popen(args,
                              close_fds=True,
                              stdin=null,
                              stdout=null,
                              stderr=stderr)
    proc.communicate(None)

  ##############################################################################
  ##  Bits

  def _CheckSettingsBeforeRun(self):
    if not self._hostname:
      raise ValueError('hostname is not set')

  def _BuildSSHArgs(self):
    args = ['ssh', '-T', '-p', '%d' % self._port]
    if self._identity_file:
      args.extend(['-i', self._identity_file])
    if not self._check_ssh_host_key:
      args.extend(['-o', 'StrictHostKeyChecking=no',
                   '-o', 'UserKnownHostsFile=/dev/null'])
    if self._multiplex:
      args.extend(['-o', 'ControlMaster=auto',
                   '-o', 'ControlPath=/tmp/catnip-ssh.%u.%r@%h:%p',
                   '-o', 'ControlPersist=yes'])
    args.append('%s@%s' % (self._username, self._hostname))
    return args

  def _BuildRunArgs(self):
    return ['sudo', 'catnip-run']

  def _BuildGetStatusArgs(self):
    return ['sudo', 'catnip-status']

  def _BuildEndMultiplexArgs(self):
    return ['-o', 'ControlPath=/tmp/catnip-ssh.%u.%r@%h:%p',
            '-O', 'exit']
