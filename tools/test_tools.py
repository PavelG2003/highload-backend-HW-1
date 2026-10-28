import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from generate_dashboard import build_dashboard, discover_handlers, request_json
from load import Load


class ToolsTest(unittest.TestCase):
    def test_dashboard_aggregates_buckets_and_supports_arbitrary_routes(self):
        dashboard = build_dashboard([("PATCH", '/new/{key}'), ("POST", "/different")])
        self.assertFalse(dashboard["editable"])
        self.assertEqual(len(dashboard["panels"]), 6)
        quantiles = dashboard["panels"][0]["targets"]
        self.assertEqual(len(quantiles), 3)
        for target in quantiles:
            self.assertIn("sum by (le) (rate(", target["expr"])
            self.assertIn('route="/new/{key}"', target["expr"])
            self.assertIn('${datacenter:regex}', target["expr"])
            self.assertIn('${pod:regex}', target["expr"])
        self.assertIn('sum by (status)', dashboard["panels"][2]["targets"][0]["expr"])
        for variable in dashboard["templating"]["list"]:
            self.assertTrue(variable["multi"])
            self.assertTrue(variable["includeAll"])

    def test_generator_discovers_catalog_and_posts_dashboard_over_http(self):
        received = []

        class FakeApi(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'[{"method":"DELETE","path":"/new/{id}"}]')

            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"success","url":"/d/generated"}')

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeApi)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            handlers = discover_handlers(url)
            result = request_json(url + "/api/dashboards/db", {
                "dashboard": build_dashboard(handlers), "overwrite": True,
            })
            self.assertEqual(result["status"], "success")
            self.assertEqual(received[0]["dashboard"]["panels"][0]["title"], "DELETE /new/{id} · latency")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_load_keeps_replica_ids_separate_and_generates_two_errors(self):
        load = Load(["http://first", "http://second"], 0)
        load.ids["http://first"].append(11)
        load.ids["http://second"].append(22)
        with patch("load.random.random", return_value=0.5), patch("load.http_request", return_value=(200, {})) as request:
            load.request(0)
            load.request(1)
            self.assertEqual(request.call_args_list[0].args, ("http://first", "GET", "/items/11"))
            self.assertEqual(request.call_args_list[1].args, ("http://second", "GET", "/items/22"))
        load.error_fraction = 1
        with patch("load.random.random", side_effect=[0, 0, 0, 0.9]), patch("load.http_request", side_effect=[(404, None), (400, None)]):
            load.request(0)
            load.request(1)
        self.assertEqual(load.statuses["404"], 1)
        self.assertEqual(load.statuses["400"], 1)


if __name__ == "__main__":
    unittest.main()
