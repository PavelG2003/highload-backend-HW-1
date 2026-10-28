package ru.itmo.items;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ItemStore {
    private final ConcurrentHashMap<Long, Item> items = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong();

    public Item create(ItemRequest request) {
        long id = nextId.incrementAndGet();
        Item item = new Item(id, request.name(), request.description());
        items.put(id, item);
        return item;
    }

    public Item get(long id) {
        Item item = items.get(id);
        if (item == null) throw notFound(id);
        return item;
    }

    public Item update(long id, ItemRequest request) {
        Item updated = items.computeIfPresent(id,
                (key, previous) -> new Item(key, request.name(), request.description()));
        if (updated == null) throw notFound(id);
        return updated;
    }

    private ResponseStatusException notFound(long id) {
        return new ResponseStatusException(HttpStatus.NOT_FOUND, "Item " + id + " not found");
    }
}
