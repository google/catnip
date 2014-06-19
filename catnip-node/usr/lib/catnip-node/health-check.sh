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

umask 022

exec 3> /var/cache/catnip-node/lock/health-check
flock -x 3

if [[ ! -f /var/cache/catnip-node/state/setup ]]; then
  # Do not perform health checks.
  exit 0
fi

exec > /var/log/catnip-health-check.log 2>&1

echo "Health check at $(LANG=C date)"

catnip-test

if [[ $? = 0 ]]; then
  echo 'healthy' > /var/cache/catnip-node/state/health
  echo 'Marked as healthy.'
else
  echo 'unhealthy' > /var/cache/catnip-node/state/health
  echo 'Marked as unhealthy.'
fi
