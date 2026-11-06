// Adapted from the MIT/Apache-2.0-licensed upstream Humantime regression
// assertions added in ed7cc7dcd2566facfce2a1a6af8087993d1887c3.
use std::time::Duration;
use subject::{parse_duration, DurationError};

#[test]
fn maximum_seconds_plus_one_thousand_milliseconds_returns_error() {
    assert_eq!(parse_duration(&format!("{}s1000ms", u64::MAX)), Err(DurationError::NumberOverflow));
}

#[test]
fn maximum_seconds_plus_split_nanoseconds_returns_error() {
    assert_eq!(parse_duration(&format!("{}s 999999999ns 1ns", u64::MAX)), Err(DurationError::NumberOverflow));
}

#[test]
fn just_below_carry_remains_representable() {
    assert_eq!(parse_duration(&format!("{}s999999999ns", u64::MAX)), Ok(Duration::new(u64::MAX, 999_999_999)));
}

#[test]
fn carry_below_maximum_remains_representable() {
    assert_eq!(parse_duration(&format!("{}s1000ms", u64::MAX - 1)), Ok(Duration::new(u64::MAX, 0)));
}

#[test]
fn ordinary_carry_remains_representable() {
    assert_eq!(parse_duration("1s1000ms"), Ok(Duration::new(2, 0)));
}

#[test]
fn larger_overflow_is_also_reported() {
    assert_eq!(parse_duration(&format!("{}s1001ms", u64::MAX)), Err(DurationError::NumberOverflow));
}
