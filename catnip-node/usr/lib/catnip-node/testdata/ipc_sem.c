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

#include <fcntl.h>
#include <semaphore.h>
#include <stdio.h>

int main(void) {
  sem_t* sem;
  sem = sem_open("/ipc-sem", O_RDWR|O_CREAT, 0700, 28);
  if (sem == SEM_FAILED) {
    puts("sem_open failed");
    return 1;
  }
  sem_close(sem);
  sem_unlink("/ipc-sem");
  return 0;
}
