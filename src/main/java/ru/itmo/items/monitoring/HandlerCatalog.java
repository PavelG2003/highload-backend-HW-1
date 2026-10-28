package ru.itmo.items.monitoring;

import java.util.Comparator;
import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

@Component
public class HandlerCatalog {
    public record Handler(String method, String path) {}
    private final RequestMappingHandlerMapping mappings;

    public HandlerCatalog(@Qualifier("requestMappingHandlerMapping") RequestMappingHandlerMapping mappings) {
        this.mappings = mappings;
    }

    public List<Handler> handlers() {
        return mappings.getHandlerMethods().entrySet().stream()
                .filter(entry -> AnnotatedElementUtils.hasAnnotation(
                        entry.getValue().getBeanType(), MonitoredApi.class))
                .flatMap(entry -> entry.getKey().getMethodsCondition().getMethods().stream()
                        .flatMap(method -> entry.getKey().getPatternValues().stream()
                                .map(path -> new Handler(method.name(), path))))
                .distinct()
                .sorted(Comparator.comparing(Handler::path).thenComparing(Handler::method))
                .toList();
    }

    public boolean contains(String method, String path) {
        return handlers().contains(new Handler(method, path));
    }
}
