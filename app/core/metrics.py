"""Small in-process Prometheus registry for operational signals.

This intentionally has no third-party dependency. Deployments with multiple
workers should scrape every worker or replace it with a shared metrics backend.
"""

import math
import re
from collections import defaultdict
from threading import Lock
from typing import Mapping

MetricKey = tuple[str, tuple[tuple[str, str], ...]]
_lock = Lock()
_counters: dict[MetricKey, float] = defaultdict(float)
_gauges: dict[MetricKey, float] = defaultdict(float)
_summaries: dict[MetricKey, list[float]] = defaultdict(lambda: [0.0, 0.0])
_name_re = re.compile(r"[^a-zA-Z0-9_:]")


def _key(name: str, labels: Mapping[str, object]) -> MetricKey:
    safe_name = _name_re.sub("_", name)
    return safe_name, tuple(sorted((str(key), str(value)) for key, value in labels.items()))


def inc_counter(name: str, value: float = 1.0, **labels: object) -> None:
    if not math.isfinite(value):
        return
    with _lock:
        _counters[_key(name, labels)] += value


def set_gauge(name: str, value: float, **labels: object) -> None:
    if not math.isfinite(value):
        return
    with _lock:
        _gauges[_key(name, labels)] = value


def add_gauge(name: str, value: float, **labels: object) -> None:
    if not math.isfinite(value):
        return
    with _lock:
        _gauges[_key(name, labels)] += value


def observe(name: str, value: float, **labels: object) -> None:
    if not math.isfinite(value):
        return
    with _lock:
        summary = _summaries[_key(name, labels)]
        summary[0] += 1
        summary[1] += value


def _label_text(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    escaped = []
    for key, value in labels:
        safe_key = _name_re.sub("_", key)
        safe_value = value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
        escaped.append(f'{safe_key}="{safe_value}"')
    return "{" + ",".join(escaped) + "}"


def render_prometheus() -> str:
    with _lock:
        counters = dict(_counters)
        gauges = dict(_gauges)
        summaries = {key: tuple(value) for key, value in _summaries.items()}

    lines: list[str] = []
    emitted: set[tuple[str, str]] = set()
    for collection, metric_type in ((counters, "counter"), (gauges, "gauge")):
        for (name, labels), value in sorted(collection.items()):
            marker = (name, metric_type)
            if marker not in emitted:
                lines.append(f"# TYPE {name} {metric_type}")
                emitted.add(marker)
            lines.append(f"{name}{_label_text(labels)} {value:g}")
    for (name, labels), (count, total) in sorted(summaries.items()):
        marker = (name, "summary")
        if marker not in emitted:
            lines.append(f"# TYPE {name} summary")
            emitted.add(marker)
        label_text = _label_text(labels)
        lines.append(f"{name}_count{label_text} {count:g}")
        lines.append(f"{name}_sum{label_text} {total:g}")
    return "\n".join(lines) + "\n"


__all__ = ["add_gauge", "inc_counter", "observe", "render_prometheus", "set_gauge"]
