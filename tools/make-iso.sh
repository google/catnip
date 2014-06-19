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

arch=amd64

if ! which fakeroot > /dev/null 2>&1; then
  echo "requires fakeroot"
  exit 1
fi
if ! which mkisofs > /dev/null 2>&1; then
  echo "requires mkisofs"
  exit 1
fi

cd "$(dirname "$0")/.."

(
  rm -rf "installer-${arch}/work"
  mkdir "installer-${arch}/work"
  fakeroot bash -c "cd installer-${arch}/work && cat ../initrd.gz.original | gzip -d | cpio -i --quiet && cp ../preseed.cfg ./ && find . | cpio -o --quiet -H newc | gzip -c9 > ../initrd.gz"
  rm -rf "installer-${arch}/work"
)

mkisofs \
-rational-rock \
-volid "Ubuntu+Catnip Install CD" \
-cache-inodes \
-joliet \
-full-iso9660-filenames \
-eltorito-boot isolinux.bin \
-eltorito-catalog boot.cat \
-no-emul-boot \
-boot-load-size 4 \
-boot-info-table \
-exclude '*.orig' \
-output "catnip-node-${arch}.iso" \
"installer-${arch}/"

rm -f "installer-${arch}/initrd.gz"
