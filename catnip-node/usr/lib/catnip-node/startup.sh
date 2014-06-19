#!/bin/bash
#
#  Copyright 2014 Google Inc. All rights reserved
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

set -e

if [[ ! -f /var/cache/catnip-node/state/configured ]]; then
  exit 1
fi
if [[ -f /var/cache/catnip-node/state/setup ]]; then
  exit 0
fi

# First of all, ensure that no client is using sandboxes and health checkers are
# not running.
/usr/lib/catnip-node/cleanup.sh

# Mark as set up.
touch /var/cache/catnip-node/state/setup
