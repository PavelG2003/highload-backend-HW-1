"""Read-only acceptance check for a running stack; waits for the load ramp."""
import base64
import json
import math
import os
import time
import urllib.error
import urllib.parse

from generate_dashboard import discover_handlers, request_json


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def prom_query(base_url, expression, timestamp):
    query = urllib.parse.urlencode({"query": expression, "time": timestamp})
    result = request_json(base_url + "/api/v1/query?" + query)
    check(result.get("status") == "success", "Prometheus query failed")
    check(not result.get("warnings"), f"Prometheus warnings: {result.get('warnings')}")
    return result["data"]["result"]


def scalar(base_url, expression, timestamp):
    results = prom_query(base_url, expression, timestamp)
    check(len(results) == 1, f"Expected one series: {expression}")
    value = float(results[0]["value"][1])
    check(math.isfinite(value), f"Non-finite result: {expression}")
    return value


def verify(urls, prometheus, grafana, authorization):
    catalogs = []
    for url in urls:
        check(request_json(url + "/health")["status"] == "UP", f"Unhealthy app: {url}")
        catalogs.append(discover_handlers(url))
    check(all(catalog == catalogs[0] for catalog in catalogs), "Replica catalogs differ")
    handlers = catalogs[0]
    check(not any(path in ("/health", "/metrics", "/handlers") for _, path in handlers),
          "Service endpoint found in business catalog")

    targets = request_json(prometheus + "/api/v1/targets")["data"]["activeTargets"]
    targets = [target for target in targets if target["labels"].get("job") == "items"]
    check(len(targets) == len(urls) and all(target["health"] == "up" for target in targets),
          "Prometheus does not scrape every replica")
    datasource = request_json(grafana + "/api/datasources/uid/items-prometheus", authorization=authorization)
    check(datasource["type"] == "prometheus", "Wrong Grafana datasource")
    dashboard = request_json(grafana + "/api/dashboards/uid/items-golden-signals",
                             authorization=authorization)["dashboard"]
    check(dashboard["editable"] is False, "Dashboard is editable")
    check(len(dashboard["panels"]) == len(handlers) * 3, "Dashboard does not match runtime catalog")
    variables = {variable["name"]: variable for variable in dashboard["templating"]["list"]}
    for name in ("datacenter", "pod"):
        check(variables[name]["multi"] and variables[name]["includeAll"], f"Invalid selector: {name}")

    timestamp = time.time()
    total = scalar(prometheus, "sum(rate(handler_requests_total[1m]))", timestamp)
    check(20 <= total <= 50, f"Load is still ramping or outside 20–50 RPS: {total:.2f}")
    replicas = prom_query(prometheus, "sum by (datacenter, pod) (rate(handler_requests_total[1m]))", timestamp)
    check(len(replicas) == len(urls), "Missing replica labels")
    check(all(float(replica["value"][1]) > 0 for replica in replicas), "A replica receives no load")
    check(len({replica["metric"]["datacenter"] for replica in replicas}) == len(urls),
          "Expected one different datacenter per replica")
    for replica in replicas:
        selector = ",".join(f"{name}=~{json.dumps(replica['metric'][name])}" for name in ("datacenter", "pod"))
        selected = scalar(prometheus, f"sum(rate(handler_requests_total{{{selector}}}[1m]))", timestamp)
        check(math.isclose(selected, float(replica["value"][1]), rel_tol=1e-6), "Single-pod filter is incorrect")
    combined_selector = ",".join(
        f'{name}=~"' + "|".join(replica["metric"][name] for replica in replicas) + '"'
        for name in ("datacenter", "pod"))
    combined = scalar(prometheus, f"sum(rate(handler_requests_total{{{combined_selector}}}[1m]))", timestamp)
    check(math.isclose(total, combined, rel_tol=1e-6), "Multi-select RPS differs from total")

    for method, path in handlers:
        selector = f"method={json.dumps(method)},route={json.dumps(path)}"
        coverage = prom_query(prometheus, f"sum by (pod) (rate(handler_requests_total{{{selector}}}[1m]))", timestamp)
        check(len(coverage) == len(urls) and all(float(series["value"][1]) > 0 for series in coverage),
              f"Handler missing traffic on a replica: {method} {path}")
    error_rates = prom_query(prometheus, 'sum by (status) (rate(handler_requests_total{status=~"[45].."}[1m]))', timestamp)
    errors = {series["metric"]["status"]: float(series["value"][1]) for series in error_rates}
    check(errors.get("400", 0) > 0 and errors.get("404", 0) > 0, "Expected both 400 and 404 errors")
    error_fraction = sum(errors.values()) / total
    check(0.005 <= error_fraction <= 0.12, f"Unexpected error fraction: {error_fraction:.1%}")
    check(scalar(prometheus,
                 'sum(handler_requests_total{route=~"/health|/metrics|/handlers"}) or vector(0)', timestamp) == 0,
          "Service endpoints were included in metrics")

    # Exercise the actual expressions saved in Grafana against the real PromQL engine.
    queries = 0
    for panel in dashboard["panels"]:
        for target in panel["targets"]:
            expression = target["expr"].replace("${datacenter:regex}", ".*")
            expression = expression.replace("${pod:regex}", ".*").replace("$__rate_interval", "1m")
            series = prom_query(prometheus, expression, timestamp)
            if "histogram_quantile" in expression or "status=~" not in expression:
                check(bool(series), f"Empty panel: {panel['title']}")
                check(all(math.isfinite(float(value["value"][1])) for value in series),
                      f"Non-finite panel: {panel['title']}")
            queries += 1
    return {"result": "PASS", "handlers": len(handlers), "replicas": len(replicas),
            "panels": len(dashboard["panels"]), "promql_queries": queries,
            "total_rps": round(total, 2), "error_percent": round(error_fraction * 100, 2),
            "errors_rps": errors, "dashboard_editable": dashboard["editable"]}


def main():
    urls = [url.rstrip("/") for url in os.getenv("APP_URLS", "http://localhost:8080,http://localhost:8081").split(",")]
    prometheus = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
    grafana = os.getenv("GRAFANA_URL", "http://localhost:3000").rstrip("/")
    user, password = os.environ["GRAFANA_ADMIN_USER"], os.environ["GRAFANA_ADMIN_PASSWORD"]
    authorization = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
    deadline = time.monotonic() + float(os.getenv("VERIFY_TIMEOUT", "240"))
    attempt = 0
    while True:
        try:
            result = verify(urls, prometheus, grafana, authorization)
            print(json.dumps(result, indent=2), flush=True)
            return
        except (AssertionError, urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if time.monotonic() >= deadline:
                raise SystemExit(f"FAIL: {error}") from error
            if attempt % 4 == 0:
                print(f"Waiting for stack: {error}", flush=True)
            attempt += 1
            time.sleep(5)


if __name__ == "__main__":
    main()
