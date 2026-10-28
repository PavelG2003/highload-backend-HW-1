package ru.itmo.items.monitoring;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.Timer;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

/** Records once after MVC resolves the route and response, including validation/404 errors. */
@Component
public class MetricsFilter extends OncePerRequestFilter {
    private final PrometheusMeterRegistry registry;
    private final HandlerCatalog catalog;

    public MetricsFilter(PrometheusMeterRegistry registry, HandlerCatalog catalog) {
        this.registry = registry;
        this.catalog = catalog;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        long started = System.nanoTime();
        boolean failed = false;
        try {
            chain.doFilter(request, response);
        } catch (IOException | ServletException | RuntimeException | Error error) {
            failed = true;
            throw error;
        } finally {
            Object matched = request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
            if (matched != null && catalog.contains(request.getMethod(), matched.toString())) {
                String status = Integer.toString(failed ? 500 : response.getStatus());
                Tags tags = Tags.of("method", request.getMethod(), "route", matched.toString(), "status", status);
                Counter.builder("handler_requests").description("Completed business HTTP requests")
                        .tags(tags).register(registry).increment();
                Timer.builder("handler_request_duration").description("Business HTTP request duration")
                        .tags(tags)
                        .serviceLevelObjectives(Duration.ofMillis(1), Duration.ofMillis(5),
                                Duration.ofMillis(10), Duration.ofMillis(25), Duration.ofMillis(50),
                                Duration.ofMillis(100), Duration.ofMillis(250), Duration.ofMillis(500),
                                Duration.ofSeconds(1), Duration.ofSeconds(2), Duration.ofSeconds(5))
                        .register(registry).record(System.nanoTime() - started, TimeUnit.NANOSECONDS);
            }
        }
    }
}
