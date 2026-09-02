package com.example.bookshelf.service;

import com.example.bookshelf.domain.Book;
import com.example.bookshelf.domain.Loan;
import com.example.bookshelf.repository.BookRepository;
import com.example.bookshelf.repository.LoanRepository;
import java.time.LocalDate;
import java.util.List;
import java.util.NoSuchElementException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Service containing use cases for books and loans.
 */
@Service
@Transactional
public class BookshelfService {

    /** Borrow limit (number of books) per borrower. */
    private static final int MAX_BORROW_COUNT_PER_BORROWER = 5;

    /** Loan period in days. */
    private static final int LOAN_PERIOD_DAYS = 14;

    private final BookRepository bookRepository;
    private final LoanRepository loanRepository;

    public BookshelfService(BookRepository bookRepository, LoanRepository loanRepository) {
        this.bookRepository = bookRepository;
        this.loanRepository = loanRepository;
    }

    @Transactional(readOnly = true)
    public List<Book> findAllBooks() {
        return bookRepository.findAll();
    }

    @Transactional(readOnly = true)
    public List<Book> searchBooksByTitle(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            return bookRepository.findAll();
        }
        return bookRepository.findByTitleContainingIgnoreCase(keyword);
    }

    @Transactional(readOnly = true)
    public Book getBook(Long id) {
        return bookRepository.findById(id)
                .orElseThrow(() -> new NoSuchElementException("Book not found: id=" + id));
    }

    public Book registerBook(String title, String author, String isbn, int totalCopies) {
        bookRepository.findByIsbn(isbn).ifPresent(existing -> {
            throw new BookshelfException("A book with the same ISBN is already registered: " + isbn);
        });
        return bookRepository.save(new Book(title, author, isbn, totalCopies));
    }

    /**
     * Borrows a book.
     *
     * <p>TODO: Reservation support (waitlist registration when out of stock) is not implemented.</p>
     */
    public Loan borrow(Long bookId, String borrower) {
        Book book = bookRepository.findById(bookId)
                .orElseThrow(() -> new NoSuchElementException("Book not found: id=" + bookId));

        int lent = loanRepository.findByBookIdAndReturnedOnIsNull(bookId).size();
        if (book.getTotalCopies() - lent <= 0) {
            throw new BookshelfException("No available copies for borrowing: " + book.getTitle());
        }

        List<Loan> borrowerLoans = loanRepository.findByBorrowerAndReturnedOnIsNull(borrower);
        if (borrowerLoans.size() >= MAX_BORROW_COUNT_PER_BORROWER) {
            throw new BookshelfException(
                    "Borrow limit (" + MAX_BORROW_COUNT_PER_BORROWER + " books) reached: " + borrower);
        }
        LocalDate today = LocalDate.now();
        for (Loan loan : borrowerLoans) {
            if (loan.getBookId().equals(bookId)) {
                throw new BookshelfException("Cannot borrow the same book twice: " + book.getTitle());
            }
            // Do not allow a new loan if the borrower has overdue books.
            if (loan.getDueOn().isBefore(today)) {
                throw new BookshelfException("Cannot borrow due to existing overdue books: " + borrower);
            }
        }

        return loanRepository.save(new Loan(bookId, borrower, today, today.plusDays(LOAN_PERIOD_DAYS)));
    }

    public Loan giveBack(Long loanId) {
        Loan loan = loanRepository.findById(loanId)
                .orElseThrow(() -> new NoSuchElementException("Loan record not found: id=" + loanId));
        if (loan.isReturned()) {
            throw new BookshelfException("Already returned: id=" + loanId);
        }
        loan.markReturned(LocalDate.now());
        return loanRepository.save(loan);
    }

    public Loan renew(Long loanId) {
        Loan loan = loanRepository.findById(loanId)
                .orElseThrow(() -> new NoSuchElementException("Loan record not found: id=" + loanId));
        if (loan.isReturned()) {
            throw new BookshelfException("Already returned: id=" + loanId);
        }
        if (loan.getDueOn().isBefore(LocalDate.now())) {
            throw new BookshelfException("Overdue loans cannot be renewed: id=" + loanId);
        }
        loan.renew(LOAN_PERIOD_DAYS);
        return loanRepository.save(loan);
    }

    @Transactional(readOnly = true)
    public List<Loan> findOverdueLoans() {
        LocalDate today = LocalDate.now();
        return loanRepository.findByReturnedOnIsNull().stream()
                .filter(loan -> loan.getDueOn().isBefore(today))
                .toList();
    }

    // TODO: Reminder email delivery for overdue borrowers is not implemented yet.
}
