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

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <linux/unistd.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>

char g_clone_stack[8192];
char** g_child_argv;

int clone_thread(void* p) {
  execvp(g_child_argv[0], g_child_argv);
  perror(g_child_argv[0]);
  return 255;
}

int main(int argc, char** argv) {
  int i, status;

  if (argc <= 1) {
    fprintf(stderr, "no argument found\n");
    return 1;
  }

  g_child_argv = malloc(sizeof(char*) * argc);
  for (i = 0; i < argc - 1; ++i) {
    g_child_argv[i] = argv[i + 1];
  }
  g_child_argv[argc - 1] = NULL;

  if (clone(clone_thread, g_clone_stack + sizeof(g_clone_stack),
            SIGCHLD|CLONE_NEWPID, NULL) < 0) {
    perror("clone");
    return 255;
  }

  wait(&status);
  if (WIFSIGNALED(status)) {
    return 128 + WTERMSIG(status);
  }
  return WEXITSTATUS(status);
}
