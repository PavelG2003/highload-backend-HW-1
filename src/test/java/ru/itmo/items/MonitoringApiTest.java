package ru.itmo.items;

import io.micrometer.core.instrument.Meter;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import ru.itmo.items.monitoring.HandlerCatalog;
import ru.itmo.items.monitoring.MonitoredApi;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"POD_ID=test-pod", "DATACENTER=test-dc"})
@Import(MonitoringApiTest.ExtraApi.class)
class MonitoringApiTest {
    @Autowired TestRestTemplate client;
    @Autowired PrometheusMeterRegistry registry;

    // Only imported by this test: verifies discovery without changing the catalog or generator.
    @TestConfiguration
    @MonitoredApi
    public static class ExtraApi {
        @GetMapping("/test-only/{id}")
        public String extra() { return "ok"; }

        @GetMapping("/test-failure")
        public String failure() { throw new IllegalStateException("Expected test failure"); }
    }

    @Test
    void discoversNewHandlersAndExcludesServiceEndpoints() {
        var handlers = client.getForObject("/handlers", HandlerCatalog.Handler[].class);
        assertThat(handlers).contains(
                new HandlerCatalog.Handler("POST", "/items"),
                new HandlerCatalog.Handler("GET", "/items/{id}"),
                new HandlerCatalog.Handler("PUT", "/items/{id}"),
                new HandlerCatalog.Handler("GET", "/test-only/{id}"));
        assertThat(List.of(handlers)).noneMatch(handler ->
                List.of("/health", "/handlers", "/metrics").contains(handler.path()));

        client.getForObject("/health", String.class);
        client.getForObject("/metrics", String.class);
        client.getForEntity("/not-a-handler", String.class);
        assertThat(registry.getMeters()).allSatisfy(meter -> {
            assertThat(meter.getId().getTag("route")).isNotIn("/health", "/handlers", "/metrics", "/not-a-handler");
        });
    }

    @Test
    void exportsAggregatableHistogramAndCountsErrorsOnce() throws Exception {
        var item = client.postForObject("/items", new ItemRequest("Metrics", null), Item.class);
        client.getForObject("/items/" + item.id(), Item.class);
        client.getForObject("/test-only/123", String.class);
        client.getForObject("/test-only/456", String.class);
        double missingBefore = count("GET", "/items/{id}", "404");
        double badBefore = count("POST", "/items", "400");
        assertThat(client.getForEntity("/items/9223372036854775807", String.class).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(client.postForEntity("/items", new ItemRequest(" ", null), String.class).getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(client.getForEntity("/test-failure", String.class).getStatusCode())
                .isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);

        // Response bytes may reach the HTTP client just before the filter's finally block.
        for (int attempt = 0; attempt < 100 && (count("GET", "/items/{id}", "404") < missingBefore + 1
                || count("POST", "/items", "400") < badBefore + 1
                || count("GET", "/test-failure", "500") < 1); attempt++) {
            Thread.sleep(20);
        }
        assertThat(count("GET", "/items/{id}", "404")).isEqualTo(missingBefore + 1);
        assertThat(count("POST", "/items", "400")).isEqualTo(badBefore + 1);
        assertThat(count("GET", "/test-failure", "500")).isEqualTo(1);
        assertThat(count("GET", "/test-only/{id}", "200")).isEqualTo(2);

        String scrape = client.getForObject("/metrics", String.class);
        assertThat(scrape).contains("handler_requests_total{", "handler_request_duration_seconds_bucket{",
                "handler_request_duration_seconds_count{", "le=\"+Inf\"", "pod=\"test-pod\"",
                "datacenter=\"test-dc\"", "route=\"/items/{id}\"");
        assertThat(scrape).doesNotContain("route=\"/items/" + item.id() + "\"", "quantile=");
        assertThat(registry.getMeters().stream().map(Meter::getId))
                .allSatisfy(id -> assertThat(id.getTag("pod")).isEqualTo("test-pod"));
    }

    private double count(String method, String route, String status) {
        var counter = registry.find("handler_requests").tags("method", method, "route", route, "status", status).counter();
        return counter == null ? 0 : counter.count();
    }
}
