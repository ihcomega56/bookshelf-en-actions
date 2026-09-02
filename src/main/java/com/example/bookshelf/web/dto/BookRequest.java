package com.example.bookshelf.web.dto;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

/**
 * Request body for book registration.
 */
public record BookRequest(
        @NotBlank(message = "Title is required") String title,
        @NotBlank(message = "Author is required") String author,
        @NotBlank(message = "ISBN is required")
        @Pattern(regexp = "\\d{13}", message = "ISBN must be 13 digits without hyphens") String isbn,
        @Min(value = 1, message = "Total copies must be at least 1") int totalCopies) {
}
