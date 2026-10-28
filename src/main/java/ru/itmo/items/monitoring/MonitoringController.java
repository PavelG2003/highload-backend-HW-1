package ru.itmo.items.monitoring;

import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MonitoringController {
    private final PrometheusMeterRegistry registry;
    private final HandlerCatalog catalog;

    public MonitoringController(PrometheusMeterRegistry registry, HandlerCatalog catalog) {
        this.registry = registry;
        this.catalog = catalog;
    }

    @GetMapping(value = "/metrics", produces = "text/plain; version=0.0.4; charset=utf-8")
    public String metrics() {
        return registry.scrape();
    }

    @GetMapping("/handlers")
    public List<HandlerCatalog.Handler> handlers() {
        return catalog.handlers();
    }
}
