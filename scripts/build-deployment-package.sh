#!/usr/bin/env bash
# Build the combined Lambda deployment package for BOTH modules.
#
# The python3.12 runtime provides boto3 but NOT strands-agents, so the zip must
# bundle strands and its deps while EXCLUDING boto3/botocore/s3transfer so the
# runtime's own (well-tested) copies are used instead.
#
# Layout inside the zip (Lambda adds the zip root to sys.path, so top-level
# package dirs resolve as `agents.*`, `choreography.*`, `orch.*`):
#   agents/  choreography/  orch/  strands/  <transitive deps>
#
# Usage:
#   scripts/build-deployment-package.sh [output.zip]
#   PYTHON=python3.12 scripts/build-deployment-package.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$HERE/travel-agents.zip}"
PYTHON="${PYTHON:-python3}"
STRANDS_VERSION="${STRANDS_VERSION:-1.54.0}"   # version this project was verified with

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PKG="$WORK/pkg"
mkdir -p "$PKG"

echo "[1/4] venv + pip install (strands-agents==$STRANDS_VERSION, requests)"
"$PYTHON" -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet --upgrade pip
"$WORK/venv/bin/pip" install --quiet --target "$PKG" "strands-agents==$STRANDS_VERSION" requests

echo "[2/4] drop packages the Lambda runtime already provides"
rm -rf "$PKG/boto3" "$PKG/botocore" "$PKG/s3transfer"
rm -rf "$PKG/boto3-"*.dist-info "$PKG/botocore-"*.dist-info "$PKG/s3transfer-"*.dist-info

echo "[3/4] add our code (src/* goes to the zip root)"
cp -r "$HERE/src/." "$PKG/"
find "$PKG" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$PKG" -name "*.dist-info/RECORD" -delete 2>/dev/null || true

echo "[4/4] zip"
( cd "$PKG" && zip -qr "$OUT" . )

echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"
echo
echo "Upload it to the bucket the stack expects, then deploy:"
echo "  aws s3 cp $OUT s3://YOUR_CODE_BUCKET/travel-agents.zip"
echo "  aws cloudformation deploy --region us-east-1 --stack-name travel-agents \\"
echo "    --template-file $HERE/templates/travel-agents.template.yml \\"
echo "    --parameter-overrides CodeBucket=YOUR_CODE_BUCKET CodeKey=travel-agents.zip \\"
echo "    --capabilities CAPABILITY_NAMED_IAM"
