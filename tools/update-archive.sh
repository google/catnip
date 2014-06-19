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

set -ex

cd "$(dirname "$0")/../archive"

apt-ftparchive sources . > Sources
apt-ftparchive packages . > Packages
apt-ftparchive contents . > Contents-i386
apt-ftparchive release . > Release
gzip -c9 Sources > Sources.gz
gzip -c9 Packages > Packages.gz
gzip -c9 Contents-i386 > Contents-i386.gz
rm -f Release.gpg
gpg --sign -b -a -o Release.gpg Release
