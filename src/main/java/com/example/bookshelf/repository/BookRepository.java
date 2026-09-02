package com.example.bookshelf.repository;

import com.example.bookshelf.domain.Book;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {

    Optional<Book> findByIsbn(String isbn);

    // TODO: Replace with pageable search to avoid oversized responses as catalog size grows
    List<Book> findByTitleContainingIgnoreCase(String keyword);
}
