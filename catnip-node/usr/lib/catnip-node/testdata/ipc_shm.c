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

#include <sys/ipc.h>
#include <sys/shm.h>
#include <string.h>

#define BLOCK_SIZE (1024*1024)

int main(void) {
  int key;
  void *p;
  key = shmget(IPC_PRIVATE, BLOCK_SIZE, IPC_CREAT | 0600);
  if (key < 0) {
    puts("shmget failed");
    return 1;
  }
  p = shmat(key, NULL, 0);
  memset(p, 0xfa, BLOCK_SIZE);
  shmdt(p);
  return 0;
}
