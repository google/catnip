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

#define _GNU_SOURCE
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <unistd.h>

#define STACK_SIZE  (sizeof(void *) * 256)

int fn(void *arg) {
  int status;
  int depth = (int)(long)arg;
  char *stack = malloc(STACK_SIZE);
  int pid = clone(fn, stack+STACK_SIZE, CLONE_FS|CLONE_FILES|CLONE_SIGHAND|CLONE_VM|CLONE_THREAD, (void*)(long)(depth+1));
  if (pid < 0) {
    printf("%d\n", depth);
    fflush(stdout);
    kill(getpid(), SIGTERM);
  }
  pause();
  return 0;
}

int main(void) {
  fn(0);
  return 0;
}
