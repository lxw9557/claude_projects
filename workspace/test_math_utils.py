"""Tests for math_utils."""

import pytest
from math_utils import add, subtract, multiply, divide, factorial, is_prime, gcd, is_palindrome, merge_sorted_arrays


class TestAdd:
    def test_positive(self):
        assert add(2, 3) == 5

    def test_negative(self):
        assert add(-1, -2) == -3


class TestSubtract:
    def test_basic(self):
        assert subtract(5, 3) == 2

    def test_negative_result(self):
        assert subtract(2, 5) == -3


class TestMultiply:
    def test_basic(self):
        assert multiply(4, 3) == 12

    def test_zero(self):
        assert multiply(5, 0) == 0


class TestDivide:
    def test_basic(self):
        assert divide(10, 2) == 5

    def test_by_zero(self):
        with pytest.raises(ValueError, match="Cannot divide by zero"):
            divide(5, 0)


class TestFactorial:
    def test_zero(self):
        assert factorial(0) == 1

    def test_positive(self):
        assert factorial(5) == 120

    def test_negative(self):
        with pytest.raises(ValueError):
            factorial(-1)


class TestIsPrime:
    def test_zero(self):
        assert not is_prime(0)

    def test_one(self):
        assert not is_prime(1)

    def test_prime(self):
        assert is_prime(7)

    def test_composite(self):
        assert not is_prime(10)


class TestGcd:
    def test_basic(self):
        assert gcd(12, 8) == 4

    def test_coprime(self):
        assert gcd(7, 13) == 1

    def test_zero(self):
        assert gcd(0, 5) == 5

    def test_negative(self):
        assert gcd(-12, 8) == 4


class TestIsPalindrome:
    def test_simple(self):
        assert is_palindrome("racecar")

    def test_mixed_case(self):
        assert is_palindrome("A man a plan a canal Panama")

    def test_with_punctuation(self):
        assert is_palindrome("A man, a plan, a canal: Panama!")

    def test_not_palindrome(self):
        assert not is_palindrome("hello")

    def test_empty_string(self):
        assert is_palindrome("")

    def test_single_character(self):
        assert is_palindrome("a")


class TestMergeSortedArrays:
    def test_both_non_empty(self):
        assert merge_sorted_arrays([1, 3, 5], [2, 4, 6]) == [1, 2, 3, 4, 5, 6]

    def test_one_empty(self):
        assert merge_sorted_arrays([1, 2], []) == [1, 2]

    def test_both_empty(self):
        assert merge_sorted_arrays([], []) == []

    def test_duplicates(self):
        assert merge_sorted_arrays([1, 2, 2, 3], [2, 3, 4]) == [1, 2, 2, 2, 3, 3, 4]

    def test_negative_numbers(self):
        assert merge_sorted_arrays([-3, -1, 0], [-2, 1]) == [-3, -2, -1, 0, 1]
