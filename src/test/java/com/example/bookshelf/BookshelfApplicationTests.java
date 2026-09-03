package com.example.bookshelf;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

/**
 * Verifies that the application context loads.
 */
@SpringBootTest
class BookshelfApplicationTests {

    @Test
    void contextLoads() {
    }

    @Test
    void demoIntentionallyBrokenTest() {
        // NOTE: intentionally failing test for a CI/CD demo (build should fail here).
        assertEquals(1, 2);
    }
}
