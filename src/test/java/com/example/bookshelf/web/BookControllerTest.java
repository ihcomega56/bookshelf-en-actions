package com.example.bookshelf.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.bookshelf.domain.Book;
import com.example.bookshelf.domain.Loan;
import com.example.bookshelf.repository.BookRepository;
import com.example.bookshelf.repository.LoanRepository;
import com.example.bookshelf.service.BookshelfService;
import java.time.LocalDate;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/**
 * Integration tests for book-related API endpoints.
 */
@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    private MockMvc mockMvc;

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
        book = bookRepository.save(new Book("Test Book", "Author", "9784798121963", 1));
    }

    @Test
    void listBooksReturnsOk() throws Exception {
        mockMvc.perform(get("/api/books"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }

    @Test
    void invalidIsbnReturns400() throws Exception {
        mockMvc.perform(post("/api/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"Test Book","author":"Author","isbn":"123","totalCopies":1}
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void renewLoanReturnsUpdatedDueDate() throws Exception {
        Loan loan = bookshelfService.borrow(book.getId(), "alice");

        mockMvc.perform(post("/api/loans/{loanId}/renew", loan.getId()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.renewalCount").value(1))
                .andExpect(jsonPath("$.dueOn").value(loan.getDueOn().plusDays(14).toString()));
    }

    @Test
    void renewingReturnedLoanReturns409() throws Exception {
        Loan loan = bookshelfService.borrow(book.getId(), "alice");
        bookshelfService.giveBack(loan.getId());

        mockMvc.perform(post("/api/loans/{loanId}/renew", loan.getId()))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.message").value(org.hamcrest.Matchers.containsString("Already returned")));
    }

    @Test
    void renewingMissingLoanReturns404() throws Exception {
        mockMvc.perform(post("/api/loans/{loanId}/renew", Long.MAX_VALUE))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message").value(org.hamcrest.Matchers.containsString("Loan record not found")));
    }

    @Test
    void reminderPreviewUsesBookTitleWhenBookExists() throws Exception {
        loanRepository.save(new Loan(book.getId(), "alice", LocalDate.now().minusDays(10), LocalDate.now().minusDays(1)));

        mockMvc.perform(get("/api/loans/overdue/reminder-preview"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].bookId").value(book.getId()))
                .andExpect(jsonPath("$[0].bookTitle").value("Test Book"));
    }

    @Test
    void reminderPreviewUsesUnknownBookWhenBookIsMissing() throws Exception {
        loanRepository.save(new Loan(Long.MAX_VALUE, "alice", LocalDate.now().minusDays(10), LocalDate.now().minusDays(1)));

        mockMvc.perform(get("/api/loans/overdue/reminder-preview"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].bookTitle").value("Unknown book"));
    }

    @Test
    void reminderPreviewHandlesMultipleLoans() throws Exception {
        Book secondBook = bookRepository.save(new Book("Second Book", "Author", "9784798123455", 1));
        loanRepository.save(new Loan(book.getId(), "alice", LocalDate.now().minusDays(20), LocalDate.now().minusDays(10)));
        loanRepository.save(new Loan(secondBook.getId(), "bob", LocalDate.now().minusDays(12), LocalDate.now().minusDays(4)));
        loanRepository.save(new Loan(Long.MAX_VALUE, "carol", LocalDate.now().minusDays(8), LocalDate.now().minusDays(2)));

        mockMvc.perform(get("/api/loans/overdue/reminder-preview"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(3))
                .andExpect(jsonPath("$[0].bookTitle").value("Test Book"))
                .andExpect(jsonPath("$[1].bookTitle").value("Second Book"))
                .andExpect(jsonPath("$[2].bookTitle").value("Unknown book"));
    }
}
