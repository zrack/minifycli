// Adapted from the MIT-licensed upstream Lexopt test_lossy_decode assertions
// added in f4b0e90dc2a6bdcfb1dd5e65d21d16c7e14f4d50. Unix-only task.
use std::ffi::OsStr;
use std::os::unix::ffi::OsStrExt;
use subject::{Arg, Parser};

fn short_options(bytes: &[u8]) -> Vec<char> {
    let mut parser = Parser::from_args([OsStr::from_bytes(bytes)]);
    let mut options = Vec::new();
    while let Some(argument) = parser.next().unwrap() {
        match argument {
            Arg::Short(ch) => options.push(ch),
            other => panic!("expected short option, got {:?}", other),
        }
    }
    options
}

#[test]
fn incomplete_two_byte_sequence_is_one_replacement() {
    assert_eq!(short_options(b"-\xF0\x9D"), vec!['\u{fffd}']);
}

#[test]
fn invalid_prefix_recovers_at_following_ascii() {
    assert_eq!(short_options(b"-\xF0\x9Da"), vec!['\u{fffd}', 'a']);
}

#[test]
fn longer_invalid_prefix_recovers_at_following_ascii() {
    assert_eq!(short_options(b"-\xF0\x9D\x84a"), vec!['\u{fffd}', 'a']);
}

#[test]
fn separate_invalid_bytes_remain_separate() {
    assert_eq!(short_options(b"-a\xFFc\xFF\xFF"), vec!['a', '\u{fffd}', 'c', '\u{fffd}', '\u{fffd}']);
}

#[test]
fn remaining_value_is_preserved_as_original_bytes() {
    let mut parser = Parser::from_args([OsStr::from_bytes(b"-a\xFFc\xFF\xFF")]);
    assert_eq!(parser.next().unwrap(), Some(Arg::Short('a')));
    assert_eq!(parser.next().unwrap(), Some(Arg::Short('\u{fffd}')));
    assert_eq!(parser.value().unwrap(), OsStr::from_bytes(b"c\xFF\xFF"));
}

#[test]
fn valid_multibyte_option_is_unchanged() {
    assert_eq!(short_options("-aµ𝄞".as_bytes()), vec!['a', 'µ', '𝄞']);
}
