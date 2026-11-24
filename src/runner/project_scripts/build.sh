#!/bin/bash
set -euo pipefail

# Run the project's build command (commands.build) with a log and a
# notification at the end. Run it as: runner project build
#
# The build command may do anything, including replacing and restarting
# Runner itself: this script doesn't need Runner to keep running.

source "$(dirname "${BASH_SOURCE[0]}")/run.sh"
start_run build

[ -n "$RUNNER_BUILD" ] || fail "This project has no build command. Set commands.build in .runner/project.toml."
run_command "Build" "$RUNNER_BUILD"
succeed "Build finished."
