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
#include <sys/msg.h>
#include <stdio.h>

int main(void) {
  int key;
  key = msgget(IPC_PRIVATE, IPC_CREAT | 0600);
  if (key < 0) {
    puts("msgget failed");
    return 1;
  }
  return 0;
}
