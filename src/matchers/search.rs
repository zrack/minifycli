//! Compact consecutive filename/line-number matches. Never trim source spaces.

struct Match<'a> {
    file: &'a str,
    position_and_text: &'a str,
    ending: &'a str,
}

/// Group ordinary `file:line:text` or `file:line:column:text` output by path.
/// Heading, context, JSON, binary, color, and filename-only formats fall back.
/// Long source lines are shortened only when the caller explicitly opts in.
pub fn minify(input: &str, max_line_chars: Option<usize>) -> Option<String> {
    let matches: Vec<Match<'_>> = input
        .split_inclusive('\n')
        .map(parse_match)
        .collect::<Option<_>>()?;
    if matches.is_empty() {
        return None;
    }
    let default_ending = matches
        .iter()
        .find(|found| !found.ending.is_empty())
        .map_or("\n", |found| found.ending);
    let mut output = String::with_capacity(input.len());
    let mut previous = None;
    for found in matches {
        if previous != Some(found.file) {
            output.push_str(found.file);
            output.push(':');
            // A missing terminal newline still needs a separator after a new
            // heading. Preserve CRLF when the input uses it.
            output.push_str(if found.ending.is_empty() {
                default_ending
            } else {
                found.ending
            });
            previous = Some(found.file);
        }
        output.push_str("  ");
        if let Some(limit) = max_line_chars {
            output.push_str(&shorten(found.position_and_text, limit));
        } else {
            output.push_str(found.position_and_text);
        }
        output.push_str(found.ending);
    }
    (output.len() < input.len()).then_some(output)
}

fn parse_match(line: &str) -> Option<Match<'_>> {
    let (line, ending) = if let Some(line) = line.strip_suffix("\r\n") {
        (line, "\r\n")
    } else if let Some(line) = line.strip_suffix('\n') {
        (line, "\n")
    } else {
        (line, "")
    };
    if line.contains(['\0', '\u{1b}', '\r']) {
        return None;
    }
    let (file, position_and_text) = line.split_once(':')?;
    if file.is_empty()
        || file.bytes().all(|b| b.is_ascii_digit())
        || file == "--"
        || file.starts_with('{')
        || file.starts_with('[')
    {
        return None;
    }
    let (number, _) = position_and_text.split_once(':')?;
    if !positive_number(number) {
        return None;
    }
    // `C:\path:line:text` and other colon-containing filenames do not meet
    // this format. Text formats are inherently ambiguous if a filename itself
    // contains a colon followed by digits; callers should use --raw for those.
    Some(Match {
        file,
        position_and_text,
        ending,
    })
}

fn positive_number(value: &str) -> bool {
    !value.is_empty()
        && value.bytes().all(|b| b.is_ascii_digit())
        && value.bytes().any(|b| b != b'0')
}

fn shorten(position_and_text: &str, max_chars: usize) -> String {
    let (line, rest) = position_and_text.split_once(':').unwrap();
    let (position, text) = match rest.split_once(':') {
        Some((column, text)) if positive_number(column) => (
            &position_and_text[..line.len() + 1 + column.len() + 1],
            text,
        ),
        _ => (&position_and_text[..line.len() + 1], rest),
    };
    let count = text.chars().count();
    if count <= max_chars {
        return position_and_text.to_owned();
    }
    let boundary = text
        .char_indices()
        .nth(max_chars)
        .map_or(text.len(), |(index, _)| index);
    let shortened = format!(
        "{position}{}... [{} chars omitted]",
        &text[..boundary],
        count - max_chars
    );
    // A short limit and short source line can make the omission label longer
    // than the original. In that case retaining the source is more compact.
    if shortened.len() < position_and_text.len() {
        shortened
    } else {
        position_and_text.to_owned()
    }
}

#[cfg(test)]
mod tests {
    use super::minify;

    const PATH: &str = "src/quite/a/long/path/module.rs";

    #[test]
    fn groups_paths_preserving_source_and_positions() {
        let input = format!("{PATH}:10:    let x = \"a  b\";\n{PATH}:20:7:\tother  source\n");
        assert_eq!(
            minify(&input, None).unwrap(),
            format!("{PATH}:\n  10:    let x = \"a  b\";\n  20:7:\tother  source\n")
        );
    }

    #[test]
    fn does_not_reorder_nonconsecutive_paths() {
        let other = "src/another/very/long/module.rs";
        let input =
            format!("{PATH}:1:a\n{PATH}:2:b\n{other}:3:c\n{other}:4:d\n{PATH}:5:e\n{PATH}:6:f\n");
        let output = minify(&input, None).unwrap();
        assert!(output.contains(&format!("  2:b\n{other}:\n  3:c\n")));
        assert!(output.ends_with(&format!("{PATH}:\n  5:e\n  6:f\n")));
    }

    #[test]
    fn preserves_crlf_and_missing_terminal_newline() {
        let input = format!("{PATH}:1:a\r\n{PATH}:2:b");
        assert_eq!(
            minify(&input, None).unwrap(),
            format!("{PATH}:\r\n  1:a\r\n  2:b")
        );
    }

    #[test]
    fn rejects_context_json_binary_and_heading_formats() {
        for input in [
            "",
            "1:a\n2:b\n",
            "10:123:some source\n10:124:other source\n",
            "file.rs\n1:a\n2:b\n",
            "file.rs:1:a\nfile.rs-2-context\n",
            "file.rs:1:a\n--\nfile.rs:4:b\n",
            "Binary file file.bin matches\n",
            "{\"type\":\"match\",\"data\":{}}\n",
            "file.rs:0:a\n",
            "C:\\file.rs:1:a\n",
            "a:b.rs:1:a\n",
            "\u{1b}[31mfile.rs:1:a\n",
            "file.rs\0:1:a\n",
        ] {
            assert_eq!(minify(input, None), None, "{input}");
        }
    }

    #[test]
    fn unknown_line_makes_entire_input_fall_back() {
        let input = format!("{PATH}:1:a\n{PATH}:2:b\nunknown diagnostic\n");
        assert_eq!(minify(&input, None), None);
    }

    #[test]
    fn default_never_shortens_source() {
        let text = "long source ".repeat(100);
        let input = format!("{PATH}:1:{text}\n{PATH}:2:{text}\n");
        let output = minify(&input, None).unwrap();
        assert_eq!(output.matches(&text).count(), 2);
        assert!(!output.contains("chars omitted"));
    }

    #[test]
    fn opt_in_shortening_is_explicit_and_utf8_safe() {
        let text = "é🦀".repeat(100);
        let input = format!("{PATH}:1:9:{text}\n{PATH}:2:{text}\n");
        let output = minify(&input, Some(3)).unwrap();
        assert!(output.contains("  1:9:é🦀é... [197 chars omitted]\n"));
        assert!(output.contains("  2:é🦀é... [197 chars omitted]\n"));
    }

    #[test]
    fn never_returns_larger_output() {
        assert_eq!(minify("x:1:a\n", None), None);
        assert_eq!(minify("x:1:abcd\n", Some(1)), None);
    }
}
