"""Local SQLite benchmark with synthetic data; no providers, secrets or sends."""
from __future__ import annotations

import argparse
import ctypes
import gc
import json
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

from cmail.store import Store
from cmail.imap_listing import recent_uids


def handles():
    import sys
    if sys.platform != 'win32':
        return None
    count = ctypes.c_ulong()
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.GetProcessHandleCount.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    if kernel.GetProcessHandleCount(kernel.GetCurrentProcess(), ctypes.byref(count)):
        return count.value
    return None


def benchmark(root: Path, iterations: int) -> dict:
    with tempfile.TemporaryDirectory(prefix='sqlite-benchmark-', dir=root) as folder:
        store = Store(Path(folder))
        store.history('synthetic-owner')
        gc.collect()
        before = handles()
        tracemalloc.start()
        gc.disable()
        elapsed = []
        try:
            for _ in range(iterations):
                started = time.perf_counter()
                store.history('synthetic-owner')
                elapsed.append((time.perf_counter() - started) * 1000)
            retained, peak = tracemalloc.get_traced_memory()
            after = handles()
        finally:
            gc.enable()
            tracemalloc.stop()
            gc.collect()
        return {'iterations': iterations, 'medianReadMs': round(statistics.median(elapsed), 4),
                'totalReadMs': round(sum(elapsed), 3), 'pythonRetainedBytes': retained,
                'pythonPeakBytes': peak, 'handlesBefore': before, 'handlesAfter': after,
                'gcDisabledDuringReadLoop': True, 'externalEffects': False}


def uid_benchmark():
    raw = b' '.join(str(number).encode('ascii') for number in range(100000))
    result = {}
    algorithms = {'previousWholeSplit':lambda: list(reversed(raw.split()[-50:])),
                  'boundedTail':lambda: recent_uids(raw,50)}
    for name, algorithm in algorithms.items():
        tracemalloc.start()
        started = time.perf_counter()
        identifiers = algorithm()
        elapsed = (time.perf_counter() - started) * 1000
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert identifiers == [str(number).encode('ascii') for number in range(99999,99949,-1)]
        result[name] = {'elapsedMs':round(elapsed,3),'peakPythonBytes':peak,'returned':len(identifiers)}
    return result


def import_benchmark():
    script = """
import json, sys, time, tracemalloc
tracemalloc.start()
started = time.perf_counter()
import cmail
elapsed = (time.perf_counter() - started) * 1000
retained, peak = tracemalloc.get_traced_memory()
print(json.dumps({'elapsedMs': round(elapsed, 3), 'pythonRetainedBytes': retained,
    'pythonPeakBytes': peak, 'loadedModules': len(sys.modules),
    'fastapiLoaded': 'fastapi' in sys.modules}))
"""
    completed = subprocess.run([sys.executable, '-s', '-B', '-c', script],
                               check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--iterations', type=int, default=200)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 1000:
        parser.error('iterations deve estar entre 1 e 1000.')
    args.directory.mkdir(parents=True, exist_ok=True)
    result = benchmark(args.directory, args.iterations)
    result['imapUidSelection'] = uid_benchmark()
    result['freshImport'] = import_benchmark()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
