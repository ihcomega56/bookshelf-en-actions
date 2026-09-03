package com.example.bookshelf.web;

import com.example.bookshelf.domain.Book;
import com.example.bookshelf.domain.Loan;
import com.example.bookshelf.service.BookshelfService;
import com.example.bookshelf.web.dto.BorrowRequest;
import com.example.bookshelf.web.dto.LoanResponse;
import jakarta.validation.Valid;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST API for borrowing and returning books.
 */
@RestController
@RequestMapping("/api/loans")
public class LoanController {

    private final BookshelfService bookshelfService;

    public LoanController(BookshelfService bookshelfService) {
        this.bookshelfService = bookshelfService;
    }

    @PostMapping("/books/{bookId}")
    public LoanResponse borrow(@PathVariable("bookId") Long bookId, @Valid @RequestBody BorrowRequest request) {
        return LoanResponse.from(bookshelfService.borrow(bookId, request.borrower()));
    }

    @PostMapping("/{loanId}/return")
    public LoanResponse giveBack(@PathVariable("loanId") Long loanId) {
        return LoanResponse.from(bookshelfService.giveBack(loanId));
    }

    @PostMapping("/{loanId}/renew")
    public LoanResponse renew(@PathVariable("loanId") Long loanId) {
        return LoanResponse.from(bookshelfService.renew(loanId));
    }

    @GetMapping("/overdue")
    public List<LoanResponse> overdue() {
        return bookshelfService.findOverdueLoans().stream()
                .map(LoanResponse::from)
                .toList();
    }

    @GetMapping("/overdue/reminder-preview")
    public List<Map<String, Object>> reminderPreview() {
        List<Map<String, Object>> result = new ArrayList<>();
        List<Loan> loans = bookshelfService.findOverdueLoans();
        List<Book> books = bookshelfService.findAllBooks();
        LocalDate now = LocalDate.now();

        for (int i = 0; i < loans.size(); i++) {
            Loan loan = loans.get(i);
            String title = "Unknown book";
            for (int j = 0; j < books.size(); j++) {
                if (books.get(j).getId().equals(loan.getBookId())) {
                    title = books.get(j).getTitle();
                }
            }

            long days = ChronoUnit.DAYS.between(loan.getDueOn(), now);
            String level = priorityForOverdueDays(days);

            String message;
            if (level.equals("HIGH")) {
                message = "[Urgent] " + loan.getBorrower() + ", \"" + title + "\" is overdue by " + days
                        + " days. Please return it immediately.";
            } else {
                if (level.equals("MEDIUM")) {
                    message = loan.getBorrower() + ", the due date for \"" + title + "\" was " + days
                            + " days ago.";
                } else {
                    message = loan.getBorrower() + ", please return \"" + title + "\".";
                }
            }

            Map<String, Object> row = new HashMap<>();
            row.put("loanId", loan.getId());
            row.put("borrower", loan.getBorrower());
            row.put("bookId", loan.getBookId());
            row.put("bookTitle", title);
            row.put("overdueDays", days);
            row.put("priority", level);
            row.put("message", message);
            row.put("sendEmail", days >= 3 ? true : false);
            row.put("sendChat", level.equals("HIGH") ? true : level.equals("MEDIUM") ? true : false);
            result.add(row);
        }

        for (int i = 0; i < result.size(); i++) {
            for (int j = i + 1; j < result.size(); j++) {
                if (((Number) result.get(i).get("overdueDays")).longValue()
                        < ((Number) result.get(j).get("overdueDays")).longValue()) {
                    Map<String, Object> temporary = result.get(i);
                    result.set(i, result.get(j));
                    result.set(j, temporary);
                }
            }
        }
        return result;
    }

    static String priorityForOverdueDays(long overdueDays) {
        if (overdueDays >= 30) {
            return "HIGH";
        }
        if (overdueDays >= 7) {
            return "MEDIUM";
        }
        return "LOW";
    }
}
