/*
 * Copyright 2014 Google Inc. All rights reserved
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <Python.h>

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <sched.h>

static PyObject* ext_unshare(PyObject* self, PyObject* args) {
  int flags, ret;
  if (!PyArg_ParseTuple(args, "i", &flags)) {
    return NULL;
  }
  ret = unshare(flags);
  if (ret < 0) {
    return PyErr_SetFromErrno(PyExc_OSError);
  }
  Py_RETURN_NONE;
}

static PyMethodDef ext_methods[] = {
  {"unshare", (PyCFunction)ext_unshare, METH_VARARGS, NULL},
  {NULL, NULL, 0, NULL}
};

PyMODINIT_FUNC init_ext(void) {
  PyObject* m;
  m = Py_InitModule("catnip._ext", ext_methods);
  if (m == NULL) {
    return;
  }

  PyModule_AddIntConstant(m, "CLONE_NEWIPC", CLONE_NEWIPC);
  PyModule_AddIntConstant(m, "CLONE_NEWNET", CLONE_NEWNET);
  PyModule_AddIntConstant(m, "CLONE_NEWNS", CLONE_NEWNS);
  PyModule_AddIntConstant(m, "CLONE_NEWUTS", CLONE_NEWUTS);
}
