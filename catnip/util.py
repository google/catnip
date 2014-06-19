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
import copy
import fcntl
import json
import os


class LockFailed(Exception):
  pass


@contextlib.contextmanager
def Lock(path, mode):
  try:
    fd = os.open(path, os.O_CREAT|os.O_WRONLY, 0600)
  except OSError:
    raise LockFailed()
  try:
    fcntl.flock(fd, mode)
  except IOError:
    raise LockFailed()
  else:
    yield
  finally:
    try:
      fcntl.flock(fd, fcntl.LOCK_UN)
    except IOError:
      pass
    try:
      os.close(fd)
    except:
      pass


class RangeValidator(object):
  def __init__(self, min_value, max_value):
    self._min_value = min_value
    self._max_value = max_value

  def __call__(self, value):
    if not (self._min_value <= value <= self._max_value):
      raise ValueError()
    return value


class ValidatedProperty(property):
  def __init__(self, type, validator=None, default=None):
    super(ValidatedProperty, self).__init__(self.GetValue, self.SetValue)
    self._type = type
    self._validator = validator
    self._default = default
    self._storage_name = None

  default = property(lambda self: self._default)

  def SetStorageName(self, storage_name):
    self._storage_name = storage_name

  def GetValue(self, parent):
    assert self._storage_name, (
        'ValidatedProperty must be used with ValidatedStruct')
    return getattr(parent, self._storage_name)

  def SetValue(self, parent, value):
    assert self._storage_name, (
        'ValidatedProperty must be used with ValidatedStruct')
    try:
      value = self._type(value)
    except:
      raise ValueError(
          'value should be compatible with %s' % self._type.__name__)
    if self._validator:
      value = self._validator(value)
    setattr(parent, self._storage_name, value)


class ValidatedStructMeta(type):
  def __new__(mcs, name, bases, dic):
    fields = []
    for key, value in dic.items():
      if isinstance(value, ValidatedProperty):
        fields.append(key)
        value.SetStorageName('_%s_value' % key)
    dic['__fields__'] = tuple(fields)
    return type.__new__(mcs, name, bases, dic)


class ValidatedStruct(object):
  __metaclass__ = ValidatedStructMeta

  def __init__(self):
    for key in self.__fields__:
      value = copy.copy(getattr(self.__class__, key).default)
      setattr(self, '_%s_value' % key, value)

  @classmethod
  def FromJSON(cls, dump):
    obj = cls()
    data = json.loads(dump)
    for key, value in data.iteritems():
      if key in cls.__fields__:
        setattr(obj, key, value)
    return obj

  def ToJSON(self):
    data = dict([(key, getattr(self, key)) for key in self.__fields__])
    return json.dumps(data, indent=2)

  def Validate(self):
    for name in self.__fields__:
      if getattr(self, name) is None:
        return False
    return True

  def Copy(self):
    return copy.copy(self)
