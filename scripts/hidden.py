# Runs a command with no window: pythonw hidden.py <program> [args...]
# Task Scheduler opens a terminal window for console programs, even hidden ones (Windows Terminal ignores the hint),
# which would cover the game in recordings. CREATE_NO_WINDOW gives the program a console with no window; its children share it.
import subprocess, sys
sys.exit(subprocess.run(sys.argv[1:], creationflags=0x08000000).returncode)
