// Adapted from the MIT-licensed upstream Lexopt regression assertions added in
// 84d7545e4e99a60c046244d3ab9f9778637ac073. Held out of solver workspaces.
use subject::{Arg, Parser};

fn check_value_is_retained(args: &[&str]) {
    let mut parser = Parser::from_args(args.iter().copied());
    parser.next().unwrap().unwrap();
    assert!(parser.values().is_ok());
    assert_eq!(parser.value().unwrap(), "b");
    assert_eq!(parser.next().unwrap(), None);
}

#[test]
fn attached_short_value_survives_unused_iterator() {
    check_value_is_retained(&["-a=b"]);
}

#[test]
fn attached_long_value_survives_unused_iterator() {
    check_value_is_retained(&["--a=b"]);
}

#[test]
fn separate_value_survives_unused_iterator() {
    check_value_is_retained(&["-a", "b"]);
}

#[test]
fn short_chain_survives_unused_iterator() {
    let mut parser = Parser::from_args(["-ab"]);
    assert_eq!(parser.next().unwrap(), Some(Arg::Short('a')));
    assert!(parser.values().is_ok());
    assert_eq!(parser.next().unwrap(), Some(Arg::Short('b')));
    assert_eq!(parser.next().unwrap(), None);
}

#[test]
fn actually_consumed_iterator_keeps_existing_behavior() {
    let mut parser = Parser::from_args(["-a", "b", "c", "-z"]);
    assert_eq!(parser.next().unwrap(), Some(Arg::Short('a')));
    let values: Vec<_> = parser.values().unwrap().collect();
    assert_eq!(values, vec!["b", "c"]);
    assert_eq!(parser.next().unwrap(), Some(Arg::Short('z')));
}
