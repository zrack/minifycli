//! Remove redundant Git patch metadata without touching source or patch paths.

/// Minify ordinary unified Git diffs. Non-patch formats fall back unchanged.
///
/// Only `diff --git` and `index` lines in blocks with an adjacent `---`/`+++`
/// pair and a unified hunk are redundant. Binary and metadata-only blocks keep
/// their file-identifying headers.
pub fn minify(input: &str) -> Option<String> {
    let lines: Vec<&str> = input.split_inclusive('\n').collect();
    if lines.is_empty() || !body(lines[0]).starts_with("diff --git ") {
        return None;
    }

    let mut output = String::with_capacity(input.len());
    let mut start = 0;
    while start < lines.len() {
        if !body(lines[start]).starts_with("diff --git ") {
            return None;
        }
        let end = lines[start + 1..]
            .iter()
            .position(|line| body(line).starts_with("diff --git "))
            .map_or(lines.len(), |offset| start + 1 + offset);
        let block = &lines[start..end];
        let redundant = ordinary_patch_header_end(block);
        for (index, line) in block.iter().enumerate() {
            if let Some(header_end) = redundant {
                if index == 0 || (index < header_end && valid_index_line(body(line))) {
                    continue;
                }
            }
            output.push_str(line);
        }
        start = end;
    }
    (output.len() < input.len()).then_some(output)
}

fn body(line: &str) -> &str {
    let line = line.strip_suffix('\n').unwrap_or(line);
    line.strip_suffix('\r').unwrap_or(line)
}

fn ordinary_patch_header_end(block: &[&str]) -> Option<usize> {
    let old = block
        .iter()
        .position(|line| body(line).starts_with("--- "))?;
    if !body(block.get(old + 1)?).starts_with("+++ ") {
        return None;
    }
    if !block[1..old].iter().all(|line| metadata(body(line))) {
        return None;
    }
    let first_hunk = body(block.get(old + 2)?);
    if !first_hunk.starts_with("@@ -") || !first_hunk.contains(" +") {
        return None;
    }
    // In a unified patch each subsequent line has a structural prefix. Refuse
    // combined diffs, prose, or an incomplete header rather than guessing.
    if !block[old + 2..].iter().all(|line| {
        let line = body(line);
        line.starts_with("@@ -")
            || line.starts_with('+')
            || line.starts_with('-')
            || line.starts_with(' ')
            || line == "\\ No newline at end of file"
    }) {
        return None;
    }
    Some(old)
}

fn metadata(line: &str) -> bool {
    valid_index_line(line)
        || [
            "old mode ",
            "new mode ",
            "new file mode ",
            "deleted file mode ",
            "similarity index ",
            "dissimilarity index ",
            "rename from ",
            "rename to ",
            "copy from ",
            "copy to ",
        ]
        .iter()
        .any(|prefix| line.starts_with(prefix))
}

fn valid_index_line(line: &str) -> bool {
    let Some(rest) = line.strip_prefix("index ") else {
        return false;
    };
    let mut words = rest.split_whitespace();
    let Some(hashes) = words.next() else {
        return false;
    };
    let Some((old, new)) = hashes.split_once("..") else {
        return false;
    };
    let hash = |value: &str| !value.is_empty() && value.bytes().all(|b| b.is_ascii_hexdigit());
    if !hash(old) || !hash(new) {
        return false;
    }
    if let Some(mode) = words.next() {
        if mode.len() != 6 || !mode.bytes().all(|b| matches!(b, b'0'..=b'7')) {
            return false;
        }
    }
    words.next().is_none()
}

#[cfg(test)]
mod tests {
    use super::minify;

    const PATCH: &str = "diff --git a/src/a.rs b/src/a.rs\nindex abcd123..deaf456 100644\n--- a/src/a.rs\n+++ b/src/a.rs\n@@ -1,2 +1,2 @@ fn main()\n-    let x = \"a  b\";\n+    let x = \"a   b\";\n \tkeep  whitespace\n";

    #[test]
    fn removes_only_redundant_metadata() {
        let result = minify(PATCH).unwrap();
        assert_eq!(
            result,
            PATCH.lines().skip(2).collect::<Vec<_>>().join("\n") + "\n"
        );
        assert!(result.contains("+    let x = \"a   b\";"));
        assert!(result.contains(" \tkeep  whitespace"));
    }

    #[test]
    fn retains_crlf_and_missing_terminal_newline() {
        let input = PATCH.trim_end_matches('\n').replace('\n', "\r\n");
        let result = minify(&input).unwrap();
        assert!(result.starts_with("--- a/src/a.rs\r\n+++ b/src/a.rs\r\n"));
        assert!(result.ends_with(" \tkeep  whitespace"));
        assert_eq!(result.matches('\n').count(), result.matches("\r\n").count());
    }

    #[test]
    fn preserves_mode_and_rename_metadata() {
        let input = PATCH.replace(
            "index abcd123..deaf456 100644\n",
            "old mode 100644\nnew mode 100755\nrename from src/a.rs\nrename to src/b.rs\nindex abcd123..deaf456\n",
        );
        let result = minify(&input).unwrap();
        assert!(result.contains("old mode 100644\nnew mode 100755\n"));
        assert!(result.contains("rename from src/a.rs\nrename to src/b.rs\n"));
    }

    #[test]
    fn binary_and_metadata_only_blocks_are_untouched() {
        let binary = "diff --git a/a.png b/a.png\nindex abcd..1234 100644\nBinary files a/a.png and b/a.png differ\n";
        assert_eq!(minify(binary), None);
        let mode = "diff --git a/run b/run\nold mode 100644\nnew mode 100755\n";
        assert_eq!(minify(mode), None);
        let mixed = format!("{PATCH}{binary}{mode}");
        let result = minify(&mixed).unwrap();
        assert!(result.ends_with(&format!("{binary}{mode}")));
    }

    #[test]
    fn preserves_no_newline_marker() {
        let input = format!("{PATCH}\\ No newline at end of file\n");
        assert!(minify(&input)
            .unwrap()
            .ends_with("\\ No newline at end of file\n"));
    }

    #[test]
    fn unknown_or_incomplete_formats_are_not_rewritten() {
        for input in [
            "",
            " src/a.rs | 2 +-\n 1 file changed\n",
            "diff --cc src/a.rs\nindex abc,def..123\n",
            "diff --git a/a b/a\nindex abcd..1234 100644\n",
            "diff --git a/a b/a\nindex abcd..1234 100644\n--- a/a\n+++ b/a\n",
            "diff --git a/a b/a\ncustom extension\n--- a/a\n+++ b/a\n@@ -1 +1 @@\n-a\n+b\n",
        ] {
            assert_eq!(minify(input), None, "{input}");
        }
    }
}
