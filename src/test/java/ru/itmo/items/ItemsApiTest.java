package ru.itmo.items;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.*;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ItemsApiTest {
    @Autowired TestRestTemplate client;
    @Autowired ObjectMapper json;

    @Test
    void createReadUpdateReadAndMissingItem() throws Exception {
        ResponseEntity<String> created = client.postForEntity("/items",
                new ItemRequest("Book", "First edition"), String.class);
        assertThat(created.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        JsonNode item = json.readTree(created.getBody());
        long id = item.get("id").asLong();
        String path = "/items/" + id;
        assertThat(created.getHeaders().getLocation()).hasToString(path);
        assertThat(client.getForObject(path, Item.class))
                .isEqualTo(new Item(id, "Book", "First edition"));

        ResponseEntity<Item> updated = client.exchange(path, HttpMethod.PUT,
                new HttpEntity<>(new ItemRequest("Updated book", "Second edition")), Item.class);
        assertThat(updated.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(updated.getBody()).isEqualTo(new Item(id, "Updated book", "Second edition"));
        assertThat(client.getForObject(path, Item.class)).isEqualTo(updated.getBody());
        assertThat(client.getForEntity("/items/9223372036854775807", String.class).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void validatesInputAndDoesNotCreateOnUpdate() {
        assertThat(client.postForEntity("/items", new ItemRequest(" ", null), String.class)
                .getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(client.exchange("/items/9223372036854775807", HttpMethod.PUT,
                new HttpEntity<>(new ItemRequest("Missing", null)), String.class).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(client.getForEntity("/health", String.class).getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void storesAreIndependent() {
        ItemStore first = new ItemStore();
        Item item = first.create(new ItemRequest("Only in first instance", null));
        ItemStore second = new ItemStore();
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> second.get(item.id()))
                .isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
    }
}
