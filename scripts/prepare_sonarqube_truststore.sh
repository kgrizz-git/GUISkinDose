#!/bin/sh
# Build a Java trust store for the local SonarQube Community Build container
# with the compromised eMudhra / emSign roots removed.
#
# Inputs:
#   IMAGE   optional image reference. Defaults to the digest pinned in
#           compose.sonarqube.yaml. Pass a digest, not the floating tag:
#           the version tag on Docker Hub can move. The image must be local.
# Outputs:
#   sonarqube-truststore/cacerts next to the compose file, mode 0644.
#   The file is the image trust store minus emSign ECC Root CA - G3 and
#   AAA Certificate Services. It contains no project data or tokens.
# Requirements:
#   Docker, with that image present. This script does not start, stop, or
#   recreate the SonarQube server.
#
# Re-run this after changing the pinned server image, then recreate the
# sonarqube service. A missing or unreadable file makes Java ignore the
# mount and keep trusting the roots.

set -eu

ROOT=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
IMAGE=${IMAGE:-sonarqube@sha256:4905574ab8584dcac1a06c01cdc43a4ce9e369723ac4a7ab1d029c1bf71e6fe9}
OUT="$ROOT/sonarqube-truststore"
mkdir -p "$OUT"

docker run --rm -i --user "$(id -u):$(id -g)" --entrypoint bash \
  -v "$OUT":/out \
  "$IMAGE" -s <<'EOF'
set -eu
cp "$JAVA_HOME/lib/security/cacerts" /out/cacerts
chmod u+w /out/cacerts
keytool -list -v -keystore /out/cacerts -storepass changeit > /tmp/cacerts.txt
FPS="86:A1:EC:BA:08:9C:4A:8D:3B:BE:27:34:C6:12:BA:34:1D:81:3E:04:3C:F9:E8:A8:62:CD:5C:57:A3:6B:BE:6B
D7:A7:A0:FB:5D:7E:27:31:D7:71:E9:48:4E:BC:DE:F7:1D:5F:0C:3E:0A:29:48:78:2B:C8:3E:E0:EA:69:9E:F4"
for fp in $FPS; do
  awk -v fp="SHA256: $fp" '/^Alias name: /{a=substr($0,13)} index($0,fp){print a}' /tmp/cacerts.txt |
    while IFS= read -r alias; do
      echo "Removing alias: $alias"
      keytool -delete -keystore /out/cacerts -storepass changeit -alias "$alias"
    done
done
keytool -list -keystore /out/cacerts -storepass changeit > /tmp/cacerts-after.txt
for fp in $FPS; do
  if grep -q "$fp" /tmp/cacerts-after.txt; then
    echo "ERROR: $fp is still trusted" >&2
    exit 1
  fi
done
echo "OK: cleaned trust store written"
EOF

chmod 644 "$OUT/cacerts"
echo "Wrote $OUT/cacerts"
