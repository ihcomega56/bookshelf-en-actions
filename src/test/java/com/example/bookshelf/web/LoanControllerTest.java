package com.example.bookshelf.web;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class LoanControllerTest {

    @ParameterizedTest(name = "{0} overdue days has {1} priority")
    @CsvSource({
        "0, LOW",
        "1, LOW",
        "6, LOW",
        "7, MEDIUM",
        "29, MEDIUM",
        "30, HIGH"
    })
    void overduePriorityFollowsThresholdPolicy(long overdueDays, String expectedPriority) {
        assertThat(LoanController.priorityForOverdueDays(overdueDays)).isEqualTo(expectedPriority);
    }
}