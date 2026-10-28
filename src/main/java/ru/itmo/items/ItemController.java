package ru.itmo.items;

import jakarta.validation.Valid;
import java.net.URI;

import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import ru.itmo.items.monitoring.MonitoredApi;

@MonitoredApi
@RequiredArgsConstructor
@RequestMapping("/items")
public class ItemController {
    private final ItemStore store;

    @PostMapping
    public ResponseEntity<Item> create(@Valid @RequestBody ItemRequest request) {
        Item item = store.create(request);
        return ResponseEntity.created(URI.create("/items/" + item.id())).body(item);
    }

    @GetMapping("/{id}")
    public Item get(@PathVariable long id) {
        return store.get(id);
    }

    @PutMapping("/{id}")
    public Item update(@PathVariable long id, @Valid @RequestBody ItemRequest request) {
        return store.update(id, request);
    }
}
