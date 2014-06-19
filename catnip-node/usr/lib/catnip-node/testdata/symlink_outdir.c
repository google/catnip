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

#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>

int main(void) {
  char fdpath[256], outdir[256], cmdline[256];
  char *p;
  FILE *fp;
  int status;
  int len;

  sprintf(fdpath, "/proc/%d/fd/1", (int)getpid());
  len = readlink(fdpath, outdir, sizeof(outdir) - 1);
  if (len == -1) {
    puts("failed in readlink(2)");
    return 1;
  }
  outdir[len] = '\0';
  printf("stdout: %s\n", outdir);

  p = outdir+strlen(outdir);
  while(*p != '/')
    p--;
  *p = '\0';

  sprintf(cmdline, "rm -r \"%s\"", outdir);
  printf("executing %s\n", cmdline);
  status = system(cmdline);
  if (WEXITSTATUS(status) != 0) {
    printf("cannot delete %s.\n", outdir);
    return 1;
  }

  if (symlink("/etc", outdir) == -1) {
    puts("failed in symlink(2)");
    return 1;
  }

  return 0;
}
