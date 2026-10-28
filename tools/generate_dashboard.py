"""Discover application handlers and upsert a Grafana 12.1 classic dashboard.

No third-party dependencies or hard-coded application route list.
"""
import argparse
import base64
import json
import os
import time
import urllib.error
import urllib.request

DATASOURCE = {"type": "prometheus", "uid": "items-prometheus"}
FILTERS = 'datacenter=~"${datacenter:regex}",pod=~"${pod:regex}"'


def request_json(url, payload=None, authorization=None):
    headers = {"Accept": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def discover_handlers(app_url):
    handlers = request_json(app_url.rstrip("/") + "/handlers")
    if not isinstance(handlers, list) or not handlers:
        raise ValueError("Application returned an empty or invalid handler catalog")
    result = set()
    for handler in handlers:
        method, path = handler["method"], handler["path"]
        if not isinstance(method, str) or not isinstance(path, str) or not path.startswith("/"):
            raise ValueError("Invalid handler in catalog")
        result.add((method, path))
    return sorted(result, key=lambda handler: (handler[1], handler[0]))


def variable(name, label, query):
    return {
        "name": name, "label": label, "type": "query", "datasource": DATASOURCE,
        "definition": query, "query": {"query": query, "refId": name},
        "refresh": 2, "sort": 1, "multi": True, "includeAll": True, "allValue": ".*",
        "current": {"text": "All", "value": "$__all", "selected": True}, "options": [],
    }


def timeseries(panel_id, title, x, y, unit, queries):
    return {
        "id": panel_id, "title": title, "type": "timeseries", "datasource": DATASOURCE,
        "gridPos": {"h": 8, "w": 8, "x": x, "y": y},
        "fieldConfig": {
            "defaults": {"unit": unit, "min": 0, "custom": {"lineWidth": 2, "fillOpacity": 8}},
            "overrides": [],
        },
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom", "calcs": ["lastNotNull"]},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
        "targets": [
            {"refId": chr(65 + index), "expr": expression, "legendFormat": legend,
             "datasource": DATASOURCE, "range": True, "editorMode": "code"}
            for index, (legend, expression) in enumerate(queries)
        ],
    }


def build_dashboard(handlers, uid="items-golden-signals"):
    panels = []
    for index, (method, path) in enumerate(handlers):
        selector = f"method={json.dumps(method)},route={json.dumps(path)},{FILTERS}"
        title = f"{method} {path}"
        quantiles = [
            (f"p{percentile}",
             f"histogram_quantile({percentile / 100}, "
             f"sum by (le) (rate(handler_request_duration_seconds_bucket{{{selector}}}[$__rate_interval])))")
            for percentile in (50, 95, 99)
        ]
        panels.extend([
            timeseries(index * 3 + 1, title + " · latency", 0, index * 8, "s", quantiles),
            timeseries(index * 3 + 2, title + " · RPS", 8, index * 8, "reqps", [
                ("requests/s", f"sum(rate(handler_requests_total{{{selector}}}[$__rate_interval]))")]),
            timeseries(index * 3 + 3, title + " · errors by status", 16, index * 8, "reqps", [
                ("HTTP {{status}}", f'sum by (status) (rate(handler_requests_total{{{selector},status=~"[45].."}}[$__rate_interval]))')]),
        ])
    return {
        "uid": uid, "title": "Items · Golden signals", "schemaVersion": 41, "version": 0,
        "editable": False, "tags": ["items", "generated", "ddia"],
        "timezone": "browser", "refresh": "5s", "time": {"from": "now-15m", "to": "now"},
        "graphTooltip": 1, "panels": panels,
        "templating": {"list": [
            variable("datacenter", "Datacenter", "label_values(handler_requests_total, datacenter)"),
            variable("pod", "Pod", 'label_values(handler_requests_total{datacenter=~"${datacenter:regex}"}, pod)'),
        ]},
        "annotations": {"list": []},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-url", default=os.getenv("APP_URL", "http://localhost:8080"))
    parser.add_argument("--grafana-url", default=os.getenv("GRAFANA_URL", "http://localhost:3000"))
    parser.add_argument("--uid", default="items-golden-signals")
    args = parser.parse_args()
    user = os.environ["GRAFANA_ADMIN_USER"]
    password = os.environ["GRAFANA_ADMIN_PASSWORD"]
    authorization = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
    for attempt in range(1, 13):
        try:
            handlers = discover_handlers(args.app_url)
            dashboard = build_dashboard(handlers, args.uid)
            result = request_json(args.grafana_url.rstrip("/") + "/api/dashboards/db", {
                "dashboard": dashboard, "overwrite": True,
                "message": "Generated from the running application's handler catalog",
            }, authorization)
            if result.get("status") != "success":
                raise RuntimeError("Grafana did not confirm dashboard publication")
            print(f"Published {len(handlers)} handlers, {len(dashboard['panels'])} panels: {result['url']}")
            return
        except urllib.error.HTTPError as error:
            if 400 <= error.code < 500:
                raise RuntimeError(f"HTTP {error.code}: check configuration and credentials") from error
            if attempt == 12:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 12:
                raise
        print(f"Services not ready, retry {attempt}/12", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    main()
