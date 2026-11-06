//! Small, conservative format matchers. Unrecognized or binary output stays intact.
pub mod matchers;

use std::ffi::OsString;
use std::path::Path;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Matcher {
    Cargo,
    NpmTest,
    GitDiff,
    Search,
    Passthrough,
}

impl Matcher {
    pub fn name(self) -> &'static str {
        match self {
            Self::Cargo => "cargo",
            Self::NpmTest => "npm-test",
            Self::GitDiff => "git-diff",
            Self::Search => "search",
            Self::Passthrough => "passthrough",
        }
    }
}

/// Inspect argv, never a shell command string. Machine and watch modes bypass filters.
pub fn select_matcher(command: &[OsString]) -> Matcher {
    let Some(program) = command.first() else {
        return Matcher::Passthrough;
    };
    let Some(name) = Path::new(program).file_name().and_then(|s| s.to_str()) else {
        return Matcher::Passthrough;
    };
    let Some(args) = command[1..]
        .iter()
        .map(|s| s.to_str())
        .collect::<Option<Vec<_>>>()
    else {
        return Matcher::Passthrough;
    };
    if args.iter().any(|a| {
        matches!(
            *a,
            "--watch"
                | "--watchAll"
                | "--json"
                | "--null"
                | "--null-data"
                | "-z"
                | "-0"
                | "--nocapture"
                | "--show-output"
        ) || a.starts_with("--watch=")
            || a.starts_with("--watchAll=")
            || a.starts_with("--message-format")
            || a.starts_with("--format=")
            || a.starts_with("--reporter")
    }) {
        return Matcher::Passthrough;
    }
    match name {
        "cargo" => {
            let subcommand = args
                .first()
                .filter(|a| !a.starts_with('+'))
                .or_else(|| args.get(1));
            if matches!(subcommand, Some(&"test" | &"check" | &"build")) {
                Matcher::Cargo
            } else {
                Matcher::Passthrough
            }
        }
        "npm"
            if args.first() == Some(&"test")
                || (args.first() == Some(&"run") && args.get(1) == Some(&"test")) =>
        {
            Matcher::NpmTest
        }
        "git" if git_subcommand(&args) == Some("diff") => Matcher::GitDiff,
        "rg" | "grep" if numbered_search(name, &args) => Matcher::Search,
        _ => Matcher::Passthrough,
    }
}

/// Only enable the search renderer when argv explicitly requests line numbers
/// in an ordinary text format. Values such as `-e -n` are patterns, not flags.
/// This deliberately accepts a small set of leading options: unfamiliar flags
/// and flags following the first positional argument fall back unchanged.
fn numbered_search(program: &str, args: &[&str]) -> bool {
    let mut numbered = false;
    let mut index = 0;
    while let Some(arg) = args.get(index).copied() {
        if arg == "--" {
            return numbered;
        }
        if !arg.starts_with('-') || arg == "-" {
            // Both tools allow some flags after the pattern. Do not guess at
            // their precedence, nor mistake a later override for a file path.
            return numbered && args[index + 1..].iter().all(|arg| !arg.starts_with('-'));
        }
        if arg.starts_with("--") {
            let (flag, value) = arg
                .split_once('=')
                .map_or((arg, None), |(flag, value)| (flag, Some(value)));
            if flag == "--line-number" && value.is_none() {
                numbered = true;
            } else if search_value_option(program, flag) {
                if value.is_none() {
                    index += 1;
                    if args.get(index).is_none() {
                        return false;
                    }
                }
            } else if matches!(flag, "--color" | "--colour") {
                let value = if let Some(value) = value {
                    Some(value)
                } else {
                    index += 1;
                    args.get(index).copied()
                };
                if value != Some("never") {
                    return false;
                }
            } else if value.is_some() || !search_plain_option(program, flag) {
                return false;
            }
        } else {
            let flags = arg.as_bytes();
            let mut offset = 1;
            while let Some(flag) = flags.get(offset).copied() {
                if flag == b'n' {
                    numbered = true;
                } else if search_short_value_option(program, flag) {
                    if offset + 1 == flags.len() {
                        index += 1;
                        if args.get(index).is_none() {
                            return false;
                        }
                    }
                    // The rest of this argv element is the option's value,
                    // including any characters that happen to look like flags.
                    break;
                } else if !search_plain_short_option(program, flag) {
                    return false;
                }
                offset += 1;
            }
        }
        index += 1;
    }
    numbered
}

fn search_value_option(program: &str, option: &str) -> bool {
    matches!(option, "--regexp" | "--file" | "--max-count")
        || (program == "rg" && matches!(option, "--glob" | "--iglob" | "--type" | "--type-not"))
        || (program == "grep" && matches!(option, "--include" | "--exclude" | "--exclude-dir"))
}

fn search_short_value_option(program: &str, flag: u8) -> bool {
    matches!(flag, b'e' | b'f' | b'm') || (program == "rg" && matches!(flag, b'g' | b't' | b'T'))
}

fn search_plain_option(program: &str, option: &str) -> bool {
    matches!(
        option,
        "--ignore-case"
            | "--fixed-strings"
            | "--invert-match"
            | "--word-regexp"
            | "--line-regexp"
            | "--with-filename"
            | "--no-messages"
            | "--text"
    ) || (program == "rg"
        && matches!(
            option,
            "--case-sensitive"
                | "--smart-case"
                | "--pcre2"
                | "--hidden"
                | "--no-ignore"
                | "--no-ignore-vcs"
                | "--no-ignore-parent"
                | "--follow"
                | "--no-config"
                | "--no-heading"
        ))
        || (program == "grep"
            && matches!(
                option,
                "--extended-regexp"
                    | "--basic-regexp"
                    | "--perl-regexp"
                    | "--recursive"
                    | "--dereference-recursive"
            ))
}

fn search_plain_short_option(program: &str, flag: u8) -> bool {
    matches!(flag, b'i' | b's' | b'F' | b'v' | b'w' | b'x' | b'H' | b'a')
        || (program == "rg" && matches!(flag, b'S' | b'P' | b'u' | b'L'))
        || (program == "grep" && matches!(flag, b'E' | b'G' | b'P' | b'r' | b'R' | b'I'))
}

fn git_subcommand<'a>(args: &'a [&str]) -> Option<&'a str> {
    let mut index = 0;
    while let Some(arg) = args.get(index) {
        match *arg {
            "-C" | "-c" | "--git-dir" | "--work-tree" | "--namespace" => index += 2,
            "--no-pager" | "--no-optional-locks" | "--literal-pathspecs" => index += 1,
            s if s.starts_with("--git-dir=")
                || s.starts_with("--work-tree=")
                || s.starts_with("--namespace=") =>
            {
                index += 1
            }
            s if !s.starts_with('-') => return Some(s),
            _ => return None,
        }
    }
    None
}

/// Return original bytes whenever a parser is uncertain, data is not UTF-8,
/// or the proposed rendering would expand the output.
pub fn minify(
    input: &[u8],
    matcher: Matcher,
    failed: bool,
    max_line_chars: Option<usize>,
) -> Vec<u8> {
    if input.contains(&0) {
        return input.to_vec();
    }
    let Ok(text) = std::str::from_utf8(input) else {
        return input.to_vec();
    };
    let candidate = match matcher {
        Matcher::Cargo => matchers::tests::minify(text, matchers::tests::TestKind::Cargo, failed),
        Matcher::NpmTest => matchers::tests::minify(text, matchers::tests::TestKind::Npm, failed),
        Matcher::GitDiff => matchers::git::minify(text),
        Matcher::Search => matchers::search::minify(text, max_line_chars),
        Matcher::Passthrough => None,
    };
    match candidate {
        Some(output) if output.len() < input.len() => output.into_bytes(),
        _ => input.to_vec(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn detect(args: &[&str]) -> Matcher {
        select_matcher(&args.iter().map(OsString::from).collect::<Vec<_>>())
    }

    #[test]
    fn recognizes_only_supported_commands() {
        assert_eq!(detect(&["cargo", "test"]), Matcher::Cargo);
        assert_eq!(detect(&["cargo", "+stable", "check"]), Matcher::Cargo);
        assert_eq!(
            detect(&["/usr/bin/git", "-C", "a b", "diff"]),
            Matcher::GitDiff
        );
        assert_eq!(
            detect(&["git", "-c", "diff.algorithm=patience", "diff"]),
            Matcher::GitDiff
        );
        assert_eq!(detect(&["npm", "run", "test"]), Matcher::NpmTest);
        assert_eq!(detect(&["rg", "-n", "TODO"]), Matcher::Search);
        assert_eq!(detect(&["echo", "cargo test"]), Matcher::Passthrough);
        assert_eq!(detect(&["git", "log", "diff"]), Matcher::Passthrough);
        assert_eq!(detect(&["cargo", "run"]), Matcher::Passthrough);
    }

    #[test]
    fn machine_and_watch_formats_are_passthrough() {
        for command in [
            vec!["cargo", "test", "--message-format=json"],
            vec!["npm", "test", "--", "--watch"],
            vec!["npm", "test", "--", "--reporter=json"],
            vec!["rg", "--json", "abc"],
            vec!["grep", "-z", "abc"],
            vec!["cargo", "test", "--", "--nocapture"],
            vec!["cargo", "test", "--", "--show-output"],
        ] {
            assert_eq!(detect(&command), Matcher::Passthrough);
        }
    }

    #[test]
    fn search_requires_an_explicit_numbered_text_format() {
        for command in [
            vec!["grep", "-H", "123:", "src"],
            vec!["rg", "word", "src"],
            vec!["rg", "-e", "-n", "src"],
            vec!["grep", "--regexp=-n", "src"],
            vec!["rg", "-g", "-n", "word"],
            vec!["rg", "word", "-n"],
        ] {
            assert_eq!(detect(&command), Matcher::Passthrough, "{command:?}");
        }
    }

    #[test]
    fn search_skips_pattern_and_glob_values_without_reading_them_as_flags() {
        for command in [
            vec!["rg", "-n", "-e", "-n", "src"],
            vec!["rg", "-e", "-n", "-n", "src"],
            vec!["rg", "-n", "-g", "*.rs", "word", "src"],
            vec!["rg", "-n", "--glob=*.rs", "word", "src"],
            vec!["rg", "-n", "--", "-pattern", "-path"],
            vec!["grep", "-RnH", "word", "src"],
            vec!["rg", "-ine", "word", "src"],
            vec!["grep", "--line-number", "--regexp=word", "src"],
        ] {
            assert_eq!(detect(&command), Matcher::Search, "{command:?}");
        }
    }

    #[test]
    fn search_machine_context_and_override_options_bypass_even_in_combinations() {
        for command in [
            vec!["rg", "-nN", "word"],
            vec!["rg", "-n", "--no-line-number", "word"],
            vec!["rg", "-n", "word", "--no-line-number"],
            vec!["rg", "-nz", "word"],
            vec!["grep", "-nZ", "word"],
            vec!["grep", "-nl", "word"],
            vec!["grep", "-nc", "word"],
            vec!["grep", "-nq", "word"],
            vec!["rg", "-n", "--vimgrep", "word"],
            vec!["rg", "-n", "--files"],
            vec!["rg", "-nA2", "word"],
            vec!["grep", "-n", "--context=2", "word"],
            vec!["rg", "-n", "--no-filename", "word"],
            vec!["grep", "-nh", "word"],
            vec!["rg", "-no", "word"],
        ] {
            assert_eq!(detect(&command), Matcher::Passthrough, "{command:?}");
        }
    }

    #[test]
    fn binary_is_byte_exact() {
        for input in [b"a\x00b".as_slice(), b"\xff\xfe".as_slice()] {
            assert_eq!(minify(input, Matcher::Cargo, false, None), input);
        }
    }
}
