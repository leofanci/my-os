#!/bin/sh
# Build myOS.app's launcher from source. The compiled binary is not tracked in
# git (nobody can review a binary in a pull request), so run this once after
# cloning and again after pulling changes to webview.swift or start-server.sh.
# Needs Xcode Command Line Tools (xcode-select --install).
set -eu
cd "$(dirname "$0")/.."
APP=myOS.app
mkdir -p "$APP/Contents/MacOS"
swiftc -O -o "$APP/Contents/MacOS/myOS" "$APP/Contents/Resources/webview.swift"
# Ad-hoc local signature: covers the binary and the bundled start-server.sh.
codesign --force --sign - "$APP"
echo "Built $APP. Open it from Finder or run: open $APP"
