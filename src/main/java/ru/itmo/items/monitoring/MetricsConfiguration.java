package ru.itmo.items.monitoring;

import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsConfiguration {
    @Bean
    public PrometheusMeterRegistry prometheusRegistry(
            @Value("${POD_ID:local}") String pod,
            @Value("${DATACENTER:local}") String datacenter) {
        var registry = new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
        registry.config().commonTags("pod", pod, "datacenter", datacenter);
        return registry;
    }
}
