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

if [[ ! -f /var/cache/catnip-node/state/configured ]]; then
  exit 0
fi

# Mark as not set up.
rm -f /var/cache/catnip-node/state/setup

# Wait for all sandboxes to halt.
exec 3> /var/cache/catnip-node/lock/master
flock -x 3
exec 3>&-

# Wait for all health checkers to halt.
exec 3> /var/cache/catnip-node/lock/health-check
flock -x 3
exec 3>&-
sleep 1

rm -f /var/cache/catnip-node/state/health
