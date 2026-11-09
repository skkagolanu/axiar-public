"""Diagnostic-only deterministic profile, armed after application warm-up."""

import cProfile
import os
import pstats
import signal

import uvicorn

profile = cProfile.Profile()


def start_profile(*_):
    profile.clear()
    profile.enable()


def save_profile(*_):
    profile.disable()
    path = os.environ['AXIAR_PROFILE_PATH']
    profile.dump_stats(path)
    with open(path+'.txt','w') as stream:
        pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('tottime').print_stats(100)
        pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(100)


signal.signal(signal.SIGUSR2,start_profile)
signal.signal(signal.SIGUSR1,save_profile)
uvicorn.run('app.main:app',host='127.0.0.1',port=58089,access_log=False)
