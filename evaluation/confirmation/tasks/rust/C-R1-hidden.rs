// Regression coverage for Winnow's MIT-licensed historical correction
// 97728b3ae287f57366a814436bd82b0040785d05. Kept outside solver exports.
use subject::{Parser, PResult, Partial};
use subject::ascii::{alpha1, escaped, escaped_transform};
use subject::combinator::cut_err;
use subject::error::{ErrMode, InputError};

fn normal<'a>(input: &mut &'a str) -> PResult<&'a str, InputError<&'a str>> {
    let (text, _) = (alpha1, '!').parse_next(input)?;
    Ok(text)
}

fn partial_normal<'a>(input: &mut Partial<&'a str>) -> PResult<&'a str, InputError<Partial<&'a str>>> {
    let (text, _) = (alpha1, '!').parse_next(input)?;
    Ok(text)
}

#[test]
fn complete_recognition_restores_a_failed_normal_attempt() {
    assert_eq!(escaped(normal, '\\', "n").parse_peek("a\\n;"), Ok(("a\\n;", "")));
}

#[test]
fn partial_recognition_restores_a_failed_normal_attempt() {
    let input = Partial::new("a\\n;");
    assert_eq!(escaped(partial_normal, '\\', "n").parse_peek(input), Ok((input, "")));
}

#[test]
fn complete_transformation_restores_a_failed_normal_attempt() {
    let result: Result<(&str, String), _> = escaped_transform(normal, '\\', "n".value("\n")).parse_peek("a\\n;");
    assert_eq!(result, Ok(("a\\n;", String::new())));
}

#[test]
fn partial_transformation_restores_a_failed_normal_attempt() {
    let input = Partial::new("a\\n;");
    let result: Result<(Partial<&str>, String), _> = escaped_transform(partial_normal, '\\', "n".value("\n")).parse_peek(input);
    assert_eq!(result, Ok((input, String::new())));
}

#[test]
fn valid_normal_and_escaped_segments_remain_recognized() {
    assert_eq!(escaped(normal, '\\', "n").parse_peek("abc!\\n;"), Ok((";", "abc!\\n")));
}

#[test]
fn committed_normal_failure_remains_an_error() {
    fn committed<'a>(input: &mut &'a str) -> PResult<&'a str, InputError<&'a str>> {
        let (text, _) = (alpha1, cut_err('!')).parse_next(input)?;
        Ok(text)
    }
    assert!(matches!(escaped(committed, '\\', "n").parse_peek("a?"), Err(ErrMode::Cut(_))));
}

#[test]
fn incomplete_normal_failure_remains_incomplete() {
    assert!(matches!(escaped(partial_normal, '\\', "n").parse_peek(Partial::new("a")), Err(ErrMode::Incomplete(_))));
}
