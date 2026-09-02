package com.example.bookshelf.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDate;

/**
 * Entity representing a loan record. The returnedOn field is set when returned.
 */
@Entity
@Table(name = "loans")
public class Loan {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Long bookId;

    /**
     * Identifier of the employee who borrowed the book.
     * Because authentication is not integrated yet, the raw request value is stored.
     */
    @Column(nullable = false)
    private String borrower;

    @Column(nullable = false)
    private LocalDate borrowedOn;

    @Column(nullable = false)
    private LocalDate dueOn;

    @Column(nullable = false)
    private int renewalCount;

    private LocalDate returnedOn;

    protected Loan() {
        // For JPA
    }

    public Loan(Long bookId, String borrower, LocalDate borrowedOn, LocalDate dueOn) {
        this.bookId = bookId;
        this.borrower = borrower;
        this.borrowedOn = borrowedOn;
        this.dueOn = dueOn;
    }

    public Long getId() {
        return id;
    }

    public Long getBookId() {
        return bookId;
    }

    public String getBorrower() {
        return borrower;
    }

    public LocalDate getBorrowedOn() {
        return borrowedOn;
    }

    public LocalDate getDueOn() {
        return dueOn;
    }

    public int getRenewalCount() {
        return renewalCount;
    }

    public LocalDate getReturnedOn() {
        return returnedOn;
    }

    public boolean isReturned() {
        return returnedOn != null;
    }

    public void markReturned(LocalDate returnedOn) {
        this.returnedOn = returnedOn;
    }

    public void renew(int extensionDays) {
        dueOn = dueOn.plusDays(extensionDays);
        renewalCount++;
    }
}
