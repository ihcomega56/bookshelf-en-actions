package com.example.bookshelf.service;

/**
 * Exception for business-rule violations
 * (for example, out-of-stock or borrow-limit violations).
 */
public class BookshelfException extends RuntimeException {

    public BookshelfException(String message) {
        super(message);
    }
}
