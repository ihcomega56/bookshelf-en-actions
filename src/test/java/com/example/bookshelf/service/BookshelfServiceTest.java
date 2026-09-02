package com.example.bookshelf.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.bookshelf.domain.Book;
import com.example.bookshelf.domain.Loan;
import com.example.bookshelf.repository.BookRepository;
import com.example.bookshelf.repository.LoanRepository;
import java.time.LocalDate;
import java.util.NoSuchElementException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

/**
 * Tests for borrowing and returning use cases.
 *
 * <p>Note: coverage for the borrow limit (5 books) and overdue checks is intentionally incomplete.</p>
 */
@SpringBootTest
@Transactional
class BookshelfServiceTest {

    @Autowired
    private BookshelfService bookshelfService;

    @Autowired
    private BookRepository bookRepository;

    @Autowired
    private LoanRepository loanRepository;

    private Book book;

    @BeforeEach
    void setUp() {
        loanRepository.deleteAll();
        bookRepository.deleteAll();
        book = bookRepository.save(new Book("Domain-Driven Design", "Eric Evans", "9784798121963", 1));
    }

    @Test
    void borrowSucceedsWhenStockIsAvailable() {
        Loan loan = bookshelfService.borrow(book.getId(), "alice");

        assertThat(loan.getBookId()).isEqualTo(book.getId());
        assertThat(loan.getBorrower()).isEqualTo("alice");
        assertThat(loan.getDueOn()).isEqualTo(LocalDate.now().plusDays(14));
        assertThat(loan.isReturned()).isFalse();
    }

    @Test
    void borrowFailsWhenStockIsUnavailable() {
        bookshelfService.borrow(book.getId(), "alice");

        assertThatThrownBy(() -> bookshelfService.borrow(book.getId(), "bob"))
                .isInstanceOf(BookshelfException.class)
                .hasMessageContaining("No available copies");
    }

    @Test
    void returnedBookCanBeBorrowedAgain() {
        Loan loan = bookshelfService.borrow(book.getId(), "alice");

        Loan returned = bookshelfService.giveBack(loan.getId());

        assertThat(returned.isReturned()).isTrue();
        assertThat(bookshelfService.borrow(book.getId(), "bob")).isNotNull();
    }

    @Test
    void cannotBorrowSameBookTwice() {
        Book manyCopies = bookRepository.save(new Book("Effective Java", "Joshua Bloch", "9784621303252", 5));
        bookshelfService.borrow(manyCopies.getId(), "alice");

        assertThatThrownBy(() -> bookshelfService.borrow(manyCopies.getId(), "alice"))
                .isInstanceOf(BookshelfException.class)
                .hasMessageContaining("same book twice");
    }

    @Test
    void renewCanBeCalledTwice() {
        Loan loan = bookshelfService.borrow(book.getId(), "alice");
        LocalDate originalDueOn = loan.getDueOn();

        Loan firstRenewal = bookshelfService.renew(loan.getId());
        assertThat(firstRenewal.getDueOn()).isEqualTo(originalDueOn.plusDays(14));
        assertThat(firstRenewal.getRenewalCount()).isEqualTo(1);

        Loan secondRenewal = bookshelfService.renew(loan.getId());
        assertThat(secondRenewal.getDueOn()).isEqualTo(originalDueOn.plusDays(28));
        assertThat(secondRenewal.getRenewalCount()).isEqualTo(2);
    }

    @Test
    void cannotRenewReturnedLoan() {
        Loan loan = bookshelfService.borrow(book.getId(), "alice");
        bookshelfService.giveBack(loan.getId());

        assertThatThrownBy(() -> bookshelfService.renew(loan.getId()))
                .isInstanceOf(BookshelfException.class)
                .hasMessageContaining("Already returned");
    }

    @Test
    void cannotRenewOverdueLoan() {
        Loan overdue = loanRepository.save(new Loan(book.getId(), "alice",
                LocalDate.now().minusDays(15), LocalDate.now().minusDays(1)));

        assertThatThrownBy(() -> bookshelfService.renew(overdue.getId()))
                .isInstanceOf(BookshelfException.class)
                .hasMessageContaining("Overdue loans");
    }

    @Test
    void cannotRenewMissingLoan() {
        assertThatThrownBy(() -> bookshelfService.renew(Long.MAX_VALUE))
                .isInstanceOf(NoSuchElementException.class)
                .hasMessageContaining("Loan record not found");
    }
}
