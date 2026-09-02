package com.example.bookshelf.repository;

import com.example.bookshelf.domain.Loan;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface LoanRepository extends JpaRepository<Loan, Long> {

    List<Loan> findByBookIdAndReturnedOnIsNull(Long bookId);

    List<Loan> findByBorrowerAndReturnedOnIsNull(String borrower);

    List<Loan> findByReturnedOnIsNull();
}
