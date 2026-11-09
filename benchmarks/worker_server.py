"""Equal-config async workers behind a request-level, loopback-only balancer."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from environment import docker

PROXY = "axiar-bench-proxy"


def configuration(ports, policy):
    method = "least_conn;" if policy == "least_conn" else ""
    servers = "\n".join(f"server 127.0.0.1:{port} weight=1 max_fails=0;" for port in ports)
    return f"""
worker_processes 1;
error_log /dev/stderr warn;
pid /tmp/nginx.pid;
events {{ worker_connections 4096; }}
http {{
    access_log off;
    map $http_upgrade $connection_upgrade {{ default upgrade; '' ''; }}
    upstream axiar {{
        {method}
        {servers}
        keepalive 256;
    }}
    server {{
        listen 127.0.0.1:58089;
        location / {{
            proxy_pass http://axiar;
            proxy_http_version 1.1;
            proxy_set_header Host $http_host;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_next_upstream off;
            proxy_connect_timeout 10s;
            proxy_read_timeout 60s;
            proxy_send_timeout 60s;
            proxy_buffering off;
        }}
    }}
}}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--policy", choices=("least_conn", "round_robin"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    workers = []
    proxy_started = False

    def stop(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    ports = list(range(58100, 58100 + args.workers))
    config = args.output / "nginx.conf"
    config.write_text(configuration(ports, args.policy))
    try:
        for port in ports:
            workers.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--workers",
                        "1",
                        "--no-access-log",
                    ],
                    env=dict(os.environ),
                )
            )
        # Every backend must be ready before the public listener opens.
        deadline = time.monotonic() + 55
        pending = set(ports)
        while pending:
            if any(worker.poll() is not None for worker in workers):
                raise RuntimeError("An async worker exited during startup")
            for port in list(pending):
                try:
                    with urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=0.25) as response:
                        if response.status == 200:
                            pending.remove(port)
                except OSError:
                    pass
            if time.monotonic() > deadline:
                raise RuntimeError(f"Workers not ready: {pending}")
            time.sleep(0.1)
        docker(
            "run",
            "--detach",
            "--rm",
            "--name",
            PROXY,
            "--label",
            "axiar.benchmark=isolated",
            "--network=host",
            "--memory=128m",
            "--cpus=1",
            "--mount",
            f"type=bind,src={config},dst=/etc/nginx/nginx.conf,readonly",
            "nginx:1.28-alpine",
            "nginx",
            "-g",
            "daemon off;",
        )
        proxy_started = True
        (args.output / "proxy-inspect.json").write_text(
            json.dumps(json.loads(docker("inspect", PROXY, capture_output=True, text=True).stdout), indent=2) + "\n"
        )
        while True:
            if any(worker.poll() is not None for worker in workers):
                raise RuntimeError("An async worker exited during the experiment")
            time.sleep(0.5)
    finally:
        # The runner may signal the whole group; tolerate workers already exiting.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if proxy_started:
            try:
                docker("stop", "--time", "3", PROXY, stdout=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                # A crashed proxy must not prevent cleanup of its backend workers.
                pass
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
        for worker in workers:
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()


if __name__ == "__main__":
    main()
