// Adapted from the MIT/Apache-2.0 licensed glob correction
// 398e0935167b0a75d2d955cae4c9750869ca6972, with nearby controls.
use subject::{MatchOptions, Pattern};

fn options(hidden: bool, separators: bool) -> MatchOptions {
    MatchOptions { case_sensitive: true, require_literal_separator: separators, require_literal_leading_dot: hidden }
}

#[test]
fn recursive_prefix_does_not_start_a_tail_inside_a_segment() {
    assert!(!Pattern::new("**/.*").unwrap().matches("ab.c"));
    assert!(!Pattern::new("**/.*").unwrap().matches("abc/ab.c"));
}

#[test]
fn recursive_prefix_respects_a_leading_hidden_component() {
    assert!(!Pattern::new("**/*").unwrap().matches_with(".cache", &options(true, false)));
}

#[test]
fn recursive_prefix_respects_a_nested_hidden_component() {
    assert!(!Pattern::new("**/*").unwrap().matches_with("dir/.cache/file", &options(true, false)));
}

#[test]
fn recursive_prefix_keeps_component_boundaries_for_unicode() {
    assert!(!Pattern::new("**/needle").unwrap().matches("πneedle"));
    assert!(Pattern::new("**/needle").unwrap().matches("π/needle"));
}

#[test]
fn explicit_hidden_tail_still_matches() {
    assert!(Pattern::new("**/.*").unwrap().matches(".abc"));
    assert!(Pattern::new("**/.*").unwrap().matches("abc/.abc"));
    assert!(Pattern::new("**/.config").unwrap().matches_with("dir/.config", &options(true, false)));
}

#[test]
fn hidden_components_remain_allowed_when_the_option_is_off() {
    assert!(Pattern::new("**/*").unwrap().matches_with(".cache", &options(false, false)));
    assert!(Pattern::new("**/*").unwrap().matches_with("dir/.cache/file", &options(false, false)));
}

#[test]
fn recursive_wildcard_still_accepts_empty_and_nested_inputs() {
    let pattern = Pattern::new("**").unwrap();
    assert!(pattern.matches(""));
    assert!(pattern.matches("abc"));
    assert!(pattern.matches("abc/def"));
}

#[test]
fn ordinary_wildcard_still_obeys_literal_separator_requirement() {
    assert!(!Pattern::new("*").unwrap().matches_with("a/b", &options(false, true)));
    assert!(Pattern::new("**/b").unwrap().matches_with("a/b", &options(false, true)));
}
