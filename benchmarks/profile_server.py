"""CPU-time profile wrapper used only for diagnostic runs, never the final measurements."""

import cProfile
import os
import pstats
import signal
import sys

import uvicorn

# Uvicorn replays SIGTERM after graceful shutdown. Convert that replay into
# SystemExit so the profile's finally block can persist its diagnostic artifact.
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
profile = cProfile.Profile()
profile.enable()
try:
    uvicorn.run("app.main:app", host="127.0.0.1", port=58089, access_log=False)
finally:
    profile.disable()
    profile.dump_stats(os.environ["PROFILE_PATH"])
    with open(os.environ["PROFILE_PATH"] + ".txt", "w") as stream:
        pstats.Stats(profile, stream=stream).strip_dirs().sort_stats("tottime").print_stats(70)
        pstats.Stats(profile, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(70)
