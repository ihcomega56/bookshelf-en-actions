package com.example.bookshelf.web.dto;

import com.example.bookshelf.domain.Loan;
import java.time.LocalDate;

/**
 * Loan response.
 */
public record LoanResponse(Long id, Long bookId, String borrower, LocalDate borrowedOn, LocalDate dueOn,
    LocalDate returnedOn, int renewalCount) {

    public static LoanResponse from(Loan loan) {
        return new LoanResponse(loan.getId(), loan.getBookId(), loan.getBorrower(), loan.getBorrowedOn(),
        loan.getDueOn(), loan.getReturnedOn(), loan.getRenewalCount());
    }
}
