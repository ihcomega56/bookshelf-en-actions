package com.example.bookshelf.web.dto;

import jakarta.validation.constraints.NotBlank;

/**
 * Request body for borrowing.
 *
 * <p>TODO: Because authentication/authorization is not integrated yet, borrower is
 * accepted directly from the client. After identity integration, resolve borrower
 * from authenticated user information.</p>
 */
public record BorrowRequest(@NotBlank(message = "Borrower is required") String borrower) {
}
