package com.example.bookshelf.web.dto;

import com.example.bookshelf.domain.Book;

/**
 * Book response.
 */
public record BookResponse(Long id, String title, String author, String isbn, int totalCopies) {

    public static BookResponse from(Book book) {
        return new BookResponse(book.getId(), book.getTitle(), book.getAuthor(), book.getIsbn(),
                book.getTotalCopies());
    }
}
