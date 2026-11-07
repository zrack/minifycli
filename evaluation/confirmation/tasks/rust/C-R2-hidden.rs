// Regression coverage for Winnow's MIT-licensed historical correction
// eded0f272b54211a3deb307d886e6da64abc3766. Kept outside solver exports.
use subject::{Parser, Partial};
use subject::error::{ErrMode, InputError};
use subject::stream::StreamIsPartial;
use subject::token::take_till;

fn complete(text: &str) -> Partial<&str> {
    let mut input = Partial::new(text);
    let _ = input.complete();
    input
}

fn zero(input: Partial<&str>) -> Result<(Partial<&str>, &str), ErrMode<InputError<Partial<&str>>>> {
    take_till(0.., [';']).parse_peek(input)
}

fn one(input: Partial<&str>) -> Result<(Partial<&str>, &str), ErrMode<InputError<Partial<&str>>>> {
    take_till(1.., [';']).parse_peek(input)
}

#[test]
fn completed_zero_minimum_accepts_empty_input() {
    assert_eq!(zero(complete("")), Ok((complete(""), "")));
}

#[test]
fn completed_zero_minimum_accepts_unterminated_input() {
    assert_eq!(zero(complete("abc")), Ok((complete(""), "abc")));
}

#[test]
fn completed_zero_minimum_preserves_utf8_boundaries() {
    assert_eq!(zero(complete("αβ")), Ok((complete(""), "αβ")));
}

#[test]
fn completed_one_minimum_rejects_empty_with_backtracking_error() {
    assert!(matches!(one(complete("")), Err(ErrMode::Backtrack(_))));
}

#[test]
fn completed_one_minimum_accepts_unterminated_input() {
    assert_eq!(one(complete("abc")), Ok((complete(""), "abc")));
}

#[test]
fn completed_one_minimum_preserves_utf8_boundaries() {
    assert_eq!(one(complete("αβ")), Ok((complete(""), "αβ")));
}

#[test]
fn incomplete_zero_minimum_still_requests_more_input() {
    assert!(matches!(zero(Partial::new("abc")), Err(ErrMode::Incomplete(_))));
}

#[test]
fn incomplete_one_minimum_still_requests_more_input() {
    assert!(matches!(one(Partial::new("abc")), Err(ErrMode::Incomplete(_))));
}

#[test]
fn delimited_input_keeps_remainder_and_state() {
    assert_eq!(zero(complete("abc;tail")), Ok((complete(";tail"), "abc")));
    assert_eq!(one(Partial::new("abc;tail")), Ok((Partial::new(";tail"), "abc")));
}

#[test]
fn bounded_range_keeps_its_existing_complete_behavior() {
    let result: Result<(Partial<&str>, &str), ErrMode<InputError<Partial<&str>>>> = take_till(1..=4, [';']).parse_peek(complete("abc"));
    assert_eq!(result, Ok((complete(""), "abc")));
}
