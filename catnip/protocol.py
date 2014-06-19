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

import fnmatch
import json
import os
import sys
import tarfile
import traceback

from catnip import sandbox
from catnip import util


PROTOCOL_VERSION = 4

class RequestHeader(util.ValidatedStruct):
  protocol_version = util.ValidatedProperty(type=int)


################################################################################
##  Stream Tar Reader/Writer

TAR_RECORD_SIZE = 512


class StreamTarReader(object):
  def __init__(self, stream):
    self._stream = stream
    self._info = None
    self._size = 0

  stream = property(lambda self: self._stream)
  info = property(lambda self: self._info)

  def ReadInfo(self):
    assert not self._info
    info = tarfile.TarInfo.frombuf(self._ReadRecord())
    self._info = info
    return info

  def ReadString(self, limit=None):
    assert self._info
    padded_size = ((self._info.size + TAR_RECORD_SIZE - 1)
                   / TAR_RECORD_SIZE * TAR_RECORD_SIZE)
    if limit is None:
      read_size = padded_size
      skip_size = 0
    else:
      read_size = min(limit, padded_size)
      skip_size = padded_size - read_size
    content = self._Read(read_size)[:self._info.size]
    self._Skip(skip_size)
    self._info = None
    return content

  def ReadToStream(self, stream):
    assert self._info
    padded_size = ((self._info.size + TAR_RECORD_SIZE - 1)
                   / TAR_RECORD_SIZE * TAR_RECORD_SIZE)
    pad_size = padded_size - self._info.size
    self._ReadToStream(self._info.size, stream)
    self._Skip(pad_size)
    self._info = None

  def ReadInfoAndString(self, limit=None):
    info = self.ReadInfo()
    content = self.ReadString(limit=limit)
    return (info, content)

  def _ReadRecord(self):
    return self._Read(TAR_RECORD_SIZE)

  def _Read(self, size):
    chunks = []
    remain = size
    while remain > 0:
      buf = self._ReadCarefully(remain)
      if not buf:
        break
      chunks.append(buf)
      remain -= len(buf)
      self._size += len(buf)
    if remain > 0:
      chunks.append('\0' * remain)
      remain = 0
    return ''.join(chunks)

  def _ReadToStream(self, size, stream):
    remain = size
    while remain > 0:
      buf = self._ReadCarefully(remain)
      if not buf:
        break
      stream.write(buf)
      remain -= len(buf)
      self._size += len(buf)
    if remain > 0:
      stream.write('\0' * remain)
      remain = 0

  def _Skip(self, size):
    remain = size
    while remain > 0:
      buf = self._ReadCarefully(min(65536, remain))
      if not buf:
        break
      remain -= len(buf)
      self._size += len(buf)

  def _ReadCarefully(self, size):
    return os.read(self._stream.fileno(), size)


class StreamTarWriter(object):
  def __init__(self, stream):
    self._stream = stream
    self._size = 0

  stream = property(lambda self: self._stream)

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_value, exc_tb):
    self.Finish()
    return False

  def Finish(self):
    self._WritePadding()
    self._Write('\0' * (TAR_RECORD_SIZE * 2))
    try:
      self._stream.flush()
    except:
      pass

  def WriteString(self, archive_name, content, mode=0644):
    assert isinstance(content, str)
    self._WriteHeader(archive_name, len(content), mode)
    self._Write(content)
    self._WritePadding()

  def WriteFile(self, archive_name, filename, mode=None):
    stat = os.stat(filename)
    if mode is None:
      mode = stat.st_mode
    self._WriteHeader(archive_name, stat.st_size, mode)
    with open(filename, 'r') as f:
      remain = stat.st_size
      while remain > 0:
        size = min(remain, 65536)
        buf = f.read(size)
        if not buf:
          break
        self._Write(buf)
        remain -= len(buf)
    while remain > 0:
      size = min(remain, 65536)
      self._Write('\0' * size)
      remain -= size
    self._WritePadding()

  def _WriteHeader(self, name, size, mode):
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = mode
    info.type = tarfile.REGTYPE
    info.uid = info.gid = 0
    info.uname = info.gname = 'root'
    self._Write(info.tobuf())

  def _WritePadding(self):
    if self._size % TAR_RECORD_SIZE != 0:
      padding = TAR_RECORD_SIZE - (self._size % TAR_RECORD_SIZE)
      self._Write('\0' * padding)
    assert self._size % TAR_RECORD_SIZE == 0

  def _Write(self, binary):
    self._stream.write(binary)
    self._size += len(binary)


################################################################################
##  Request

class ProtocolError(Exception):
  pass


class RequestReader(object):
  OBJECT_TYPE_MAP = {
      'HEADER': RequestHeader,
      'PARAMS': sandbox.SandboxParams,
      'RUNS/*/PARAMS': sandbox.RunRequest,
      'PAYLOAD': None,
      }

  def __init__(self, stream):
    self._tar_reader = StreamTarReader(stream)

  def Read(self):
    header = None
    params = None
    requests = []
    while True:
      obj = self._ReadObject()
      if not obj:
        break
      if isinstance(obj, RequestHeader):
        header = obj
      if isinstance(obj, sandbox.SandboxParams):
        params = obj
      if isinstance(obj, sandbox.RunRequest):
        requests.append(obj)
    if not header:
      raise ProtocolError('HEADER not found')
    if header.protocol_version != PROTOCOL_VERSION:
      raise ProtocolError('Protocol version mismatch')
    if not params:
      raise ProtocolError('PARAMS not found')
    return params, requests

  def _ReadObject(self):
    known_object = False
    while not known_object:
      info, content = self._tar_reader.ReadInfoAndString(limit=65536)
      for name_match, object_type in self.OBJECT_TYPE_MAP.iteritems():
        if fnmatch.fnmatch(info.name, name_match):
          known_object = True
          break
    if not object_type:
      return None
    try:
      obj = object_type.FromJSON(content)
    except:
      raise ProtocolError('Failed to parse JSON')
    if not obj.Validate():
      raise ProtocolError('Failed to parse JSON')
    return obj


class RequestWriter(object):
  def __init__(self, stream):
    self._stream = stream
    self._tar_writer = StreamTarWriter(stream)
    self._request_index = 0
    self._phase = 0
    self._StartHeader()

  def Finish(self):
    self._MaybeFinishHeader()
    if self._phase == 1:
      self._tar_writer.Finish()
      self._phase = 2
      self._Flush()

  def WriteParams(self, params):
    assert self._phase == 0
    self._WriteObject(params, 'PARAMS')

  def WriteRunRequest(self, request):
    assert self._phase == 0
    self._tar_writer.WriteString(
        'RUNS/%08d/BEGIN' % self._request_index, '')
    self._WriteObject(request, 'RUNS/%08d/PARAMS' % self._request_index)
    self._tar_writer.WriteString('RUNS/%08d/END' % self._request_index, '')
    self._request_index += 1

  def WriteExtraFile(self, archive_name, filename, mode=None):
    assert self._phase <= 1
    self._MaybeFinishHeader()
    self._tar_writer.WriteFile(archive_name, filename, mode)

  def WriteDiskImage(self, stream):
    assert self._phase <= 1
    self._MaybeFinishHeader()
    while True:
      buf = stream.read(65536)
      if not buf:
        break
      self._stream.write(buf)
    self._phase = 2
    self._Flush()

  def _StartHeader(self):
    assert self._phase == 0
    data = {'protocol_version': PROTOCOL_VERSION}
    content = json.dumps(data, indent=2)
    self._tar_writer.WriteString('HEADER', content)

  def _MaybeFinishHeader(self):
    if self._phase == 0:
      self._tar_writer.WriteString('PAYLOAD', '')
      self._phase = 1

  def _WriteObject(self, obj, name):
    content = obj.ToJSON()
    self._tar_writer.WriteString(name, content)

  def _Flush(self):
    try:
      self._stream.flush()
    except:
      pass


################################################################################
##  Response

class ResponseReader(object):
  def __init__(self, stream):
    self._tar_reader = StreamTarReader(stream)

  def Read(self, callback):
    while True:
      try:
        info = self._tar_reader.ReadInfo()
      except tarfile.EOFHeaderError:
        break
      if info.name == 'ERROR':
        error = self._tar_reader.ReadString(limit=65536)
        status = {'error': error}
        try:
          while True:
            info, content = self._tar_reader.ReadInfoAndString(limit=65536)
            if info.name == 'TRACEBACK':
              status['traceback'] = content
        except tarfile.EOFHeaderError:
          pass
        callback(False, status, None)
      elif fnmatch.fnmatch(info.name, 'RUNS/*/BEGIN'):
        self._tar_reader.ReadString(limit=0)
        status = {}
        while True:
          info = self._tar_reader.ReadInfo()
          if info.name.endswith('/STATUS'):
            status = json.loads(self._tar_reader.ReadString(limit=65536))
          elif info.name.endswith('/OUTPUT'):
            callback(True, status, self._tar_reader)
            if self._tar_reader.info:
              self._tar_reader.ReadString(limit=0)
          elif info.name.endswith('/END'):
            self._tar_reader.ReadString(limit=0)
            break


class ResponseWriter(object):
  def __init__(self, stream):
    self._tar_writer = StreamTarWriter(stream)
    self._request_index = 0

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_value, exc_tb):
    self.Finish()
    return False

  def Finish(self):
    self._tar_writer.Finish()

  def WriteRunResponse(self, response):
    status_json = json.dumps(response.status, indent=2)
    self._tar_writer.WriteString(
        'RUNS/%08d/BEGIN' % self._request_index, '')
    self._tar_writer.WriteString(
        'RUNS/%08d/STATUS' % self._request_index, status_json)
    self._tar_writer.WriteFile(
        'RUNS/%08d/OUTPUT' % self._request_index, response.output_file, 0644)
    self._tar_writer.WriteString('RUNS/%08d/END' % self._request_index, '')
    self._request_index += 1

  def WriteException(self):
    exc_type, exc_value, exc_tb = sys.exc_info()
    if isinstance(exc_value, sandbox.InternalError):
      error_string = str(exc_value)
    else:
      error_string = 'unhandled exception'
    self._tar_writer.WriteString('ERROR', error_string)
    traceback_string = ''.join(
        traceback.format_exception(exc_type, exc_value, exc_tb))
    self._tar_writer.WriteString('TRACEBACK', traceback_string)
