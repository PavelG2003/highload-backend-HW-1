"""Bounded, paced HTTP load against independent in-memory application replicas."""
import collections
import concurrent.futures
import json
import os
import random
import signal
import threading
import time
import urllib.error
import urllib.request


def http_request(base_url, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base_url.rstrip("/") + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        error.close()
        return error.code, None


class Load:
    def __init__(self, urls, error_fraction):
        self.urls = urls
        self.error_fraction = error_fraction
        self.ids = {url: collections.deque(maxlen=512) for url in urls}
        self.lock = threading.Lock()
        self.statuses = collections.Counter()
        self.by_instance = collections.Counter()

    def seed(self):
        for url in self.urls:
            status, item = http_request(url, "POST", "/items", {"name": "Load seed"})
            if status != 201:
                raise RuntimeError(f"Cannot seed {url}: HTTP {status}")
            self.ids[url].append(item["id"])

    def request(self, sequence):
        url = self.urls[sequence % len(self.urls)]
        expected = None
        try:
            if random.random() < self.error_fraction:
                if random.random() < 0.5:
                    status, item = http_request(url, "GET", "/items/9223372036854775807")
                    expected = 404
                else:
                    status, item = http_request(url, "POST", "/items", {"name": " "})
                    expected = 400
            else:
                with self.lock:
                    item_id = random.choice(self.ids[url])
                operation = random.random()
                if operation < 0.2:
                    status, item = http_request(url, "POST", "/items", {"name": "Load item"})
                    expected = 201
                    if status == 201:
                        with self.lock:
                            self.ids[url].append(item["id"])
                elif operation < 0.6:
                    status, item = http_request(url, "GET", f"/items/{item_id}")
                    expected = 200
                else:
                    status, item = http_request(url, "PUT", f"/items/{item_id}",
                                              {"name": "Updated by load", "description": "Background traffic"})
                    expected = 200
            with self.lock:
                self.statuses[str(status)] += 1
                self.by_instance[url] += 1
                if status != expected:
                    self.statuses["unexpected_status"] += 1
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError):
            with self.lock:
                self.statuses["transport_error"] += 1


def main():
    urls = [url.strip() for url in os.getenv("APP_URLS", "http://localhost:8080,http://localhost:8081").split(",") if url.strip()]
    target = float(os.getenv("TARGET_RPS", "30"))
    ramp = float(os.getenv("RAMP_SECONDS", "120"))
    error_fraction = float(os.getenv("ERROR_FRACTION", "0.04"))
    if not urls or target <= 0 or ramp < 0 or not 0 <= error_fraction <= 1:
        raise ValueError("Invalid load configuration")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    load = Load(urls, error_fraction)
    load.seed()
    print(f"Load: {target} total RPS, ramp {ramp}s, errors {error_fraction:.0%}, replicas {len(urls)}", flush=True)
    started = next_due = last_report = time.monotonic()
    completed_before = sequence = dropped = 0
    pending = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        while not stop.is_set():
            now = time.monotonic()
            elapsed = now - started
            start_rps = min(2.0, target)
            rps = target if ramp == 0 else start_rps + (target - start_rps) * min(elapsed / ramp, 1)
            if now < next_due:
                stop.wait(min(next_due - now, 0.1))
                continue
            pending = {future for future in pending if not future.done()}
            if len(pending) < 64:
                pending.add(pool.submit(load.request, sequence))
                sequence += 1
            else:
                dropped += 1
            # Do not create catch-up bursts after a scheduler pause.
            next_due = max(next_due + 1 / rps, now)
            if now - last_report >= 10:
                with load.lock:
                    statuses = dict(load.statuses)
                    instances = dict(load.by_instance)
                    completed = sum(instances.values())
                measured = (completed - completed_before) / (now - last_report)
                print(json.dumps({"elapsed_s": round(elapsed), "scheduled_rps": round(rps, 1),
                                  "actual_rps": round(measured, 1), "statuses": statuses,
                                  "by_instance": instances, "dropped": dropped}), flush=True)
                completed_before, last_report = completed, now
        print("Stopping load and waiting for in-flight requests", flush=True)


if __name__ == "__main__":
    main()
