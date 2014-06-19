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

#include <signal.h>
#include <sys/prctl.h>
#include <unistd.h>

int main(void) {
  int status;
  pid_t p;
  if (p = fork()) {
    wait(&status);
  }
  else {
    if (p = fork()) {
      wait(&status);
    }
    else {
      setsid();
      prctl(PR_SET_NAME, (char*)"test-daemon", 0, 0, 0);
      kill(getppid(), SIGTERM);
      pause();
    }
  }
  return 0;
}
