//! Opt-in local transcripts. Replay only reads bytes; it never executes argv.
use crate::Matcher;
use std::collections::BTreeMap;
use std::ffi::{OsStr, OsString};
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};

const MAX_METADATA: u64 = 64 * 1024;
const FILES: [&str; 4] = [
    "stdout.raw",
    "stderr.raw",
    "stdout.filtered",
    "stderr.filtered",
];

#[derive(Clone, Copy, Debug)]
pub enum Stream {
    Stdout,
    Stderr,
}

impl Stream {
    fn index(self) -> usize {
        match self {
            Self::Stdout => 0,
            Self::Stderr => 1,
        }
    }
}

pub struct Metadata {
    pub command: Vec<OsString>,
    pub matcher: Matcher,
    pub exit_code: i32,
    pub failed: bool,
    pub cancelled: bool,
    pub spilled: [bool; 2],
    pub max_line_chars: Option<usize>,
    pub complete: bool,
}

pub struct Record {
    directory: PathBuf,
    files: [Option<File>; 4],
}

impl Record {
    /// Exclusively create a private directory. No parent directories are made
    /// and an existing path, including a symlink, is never overwritten.
    pub fn create(directory: &Path) -> io::Result<Self> {
        let mut builder = fs::DirBuilder::new();
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            builder.mode(0o700);
        }
        builder.create(directory)?;
        let mut files = [None, None, None, None];
        for (index, name) in FILES.into_iter().enumerate() {
            files[index] = Some(create_private(&directory.join(name))?);
        }
        Ok(Self {
            directory: directory.to_path_buf(),
            files,
        })
    }

    pub fn take_raw(&mut self, stream: Stream) -> io::Result<File> {
        self.take(stream.index())
    }

    pub fn take_filtered(&mut self, stream: Stream) -> io::Result<File> {
        self.take(2 + stream.index())
    }

    fn take(&mut self, index: usize) -> io::Result<File> {
        self.files[index].take().ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidInput, "record writer already taken")
        })
    }

    /// Commit metadata only after all external writers have been flushed and
    /// joined. If execution stops early, absent metadata marks the record as
    /// incomplete. Length checks detect truncation, not same-length tampering.
    pub fn finish(self, metadata: Metadata) -> io::Result<()> {
        if metadata.command.is_empty() {
            return Err(invalid("recorded argv is empty"));
        }
        for file in self.files.iter().flatten() {
            file.sync_all()?;
        }
        let mut lengths = [0; 4];
        for (index, name) in FILES.into_iter().enumerate() {
            let file = regular_file(&self.directory.join(name))?;
            lengths[index] = file.metadata()?.len();
            file.sync_all()?;
        }
        let argv = metadata
            .command
            .iter()
            .map(|arg| encode_arg(arg).map(|value| format!("\"{value}\"")))
            .collect::<io::Result<Vec<_>>>()?
            .join(", ");
        let limit = metadata
            .max_line_chars
            .map_or("null".into(), |value| value.to_string());
        let text = format!(
            "{{\n  \"schema_version\": 1,\n  \"complete\": {},\n  \"tool_version\": \"{}\",\n  \"argv_encoding\": \"{}\",\n  \"argv_hex\": [{}],\n  \"matcher\": \"{}\",\n  \"exit_code\": {},\n  \"failed\": {},\n  \"cancelled\": {},\n  \"stdout_spilled\": {},\n  \"stderr_spilled\": {},\n  \"max_line_chars\": {},\n  \"stdout_raw_bytes\": {},\n  \"stderr_raw_bytes\": {},\n  \"stdout_filtered_bytes\": {},\n  \"stderr_filtered_bytes\": {}\n}}\n",
            metadata.complete,
            env!("CARGO_PKG_VERSION"),
            encoding(),
            argv,
            metadata.matcher.name(),
            metadata.exit_code,
            metadata.failed,
            metadata.cancelled,
            metadata.spilled[0],
            metadata.spilled[1],
            limit,
            lengths[0], lengths[1], lengths[2], lengths[3],
        );
        if text.len() as u64 > MAX_METADATA {
            return Err(invalid("recorded argv exceeds metadata limit"));
        }
        // metadata.json is the completion marker. The exclusive directory and
        // create_new prevent silently replacing any previous recording.
        let temporary = self.directory.join("metadata.pending");
        let mut file = create_private(&temporary)?;
        file.write_all(text.as_bytes())?;
        file.sync_all()?;
        drop(file);
        let destination = self.directory.join("metadata.json");
        match fs::symlink_metadata(&destination) {
            Ok(_) => {
                return Err(io::Error::new(
                    io::ErrorKind::AlreadyExists,
                    "record metadata already exists",
                ))
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(error),
        }
        fs::rename(temporary, destination)?;
        Ok(())
    }
}

/// Record precisely the bytes accepted by a downstream writer. File errors
/// propagate so a transcript cannot silently claim to be complete.
pub struct TeeWriter<W> {
    inner: W,
    record: File,
}

impl<W> TeeWriter<W> {
    pub fn new(inner: W, record: File) -> Self {
        Self { inner, record }
    }
}

impl<W: Write> Write for TeeWriter<W> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let count = self.inner.write(bytes)?;
        self.record.write_all(&bytes[..count])?;
        Ok(count)
    }

    fn flush(&mut self) -> io::Result<()> {
        self.inner.flush()?;
        self.record.flush()
    }
}

#[derive(Debug)]
pub struct Replay {
    pub command: Vec<OsString>,
    pub matcher: Matcher,
    pub exit_code: i32,
    pub failed: bool,
    pub max_line_chars: Option<usize>,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
}

impl Replay {
    pub fn render(&self) -> [Vec<u8>; 2] {
        let matcher = crate::select_matcher(&self.command);
        let stderr_matcher = if matches!(matcher, Matcher::Cargo | Matcher::NpmTest) {
            matcher
        } else {
            Matcher::Passthrough
        };
        [
            crate::minify(&self.stdout, matcher, self.failed, self.max_line_chars),
            crate::minify(
                &self.stderr,
                stderr_matcher,
                self.failed,
                self.max_line_chars,
            ),
        ]
    }
}

/// Read only completed, uncancelled, unspilled records, bounded per stream.
/// Raw files remain available for inspection when a record cannot be replayed.
pub fn load_replay(directory: &Path, max_buffer: usize) -> io::Result<Replay> {
    let directory_metadata = fs::symlink_metadata(directory)?;
    if !directory_metadata.is_dir() || directory_metadata.file_type().is_symlink() {
        return Err(invalid("record path must be an ordinary directory"));
    }
    let mut text = String::new();
    regular_file(&directory.join("metadata.json"))?
        .take(MAX_METADATA + 1)
        .read_to_string(&mut text)?;
    if text.len() as u64 > MAX_METADATA {
        return Err(invalid("record metadata exceeds size limit"));
    }
    let fields = parse_fields(&text)?;
    if unsigned(field(&fields, "schema_version")?)? != 1 {
        return Err(invalid("unsupported record schema"));
    }
    if !boolean(field(&fields, "complete")?)?
        || boolean(field(&fields, "cancelled")?)?
        || boolean(field(&fields, "stdout_spilled")?)?
        || boolean(field(&fields, "stderr_spilled")?)?
    {
        return Err(invalid(
            "incomplete, cancelled, or spilled record cannot be replayed",
        ));
    }
    quoted(field(&fields, "tool_version")?)?;
    if quoted(field(&fields, "argv_encoding")?)? != encoding() {
        return Err(invalid(
            "recorded argv encoding does not match this platform",
        ));
    }
    let argv = field(&fields, "argv_hex")?;
    let values = argv
        .strip_prefix('[')
        .and_then(|value| value.strip_suffix(']'))
        .ok_or_else(|| invalid("invalid argv array"))?;
    let command = if values.trim().is_empty() {
        Vec::new()
    } else {
        values
            .split(',')
            .map(|value| decode_arg(quoted(value.trim())?))
            .collect::<io::Result<Vec<_>>>()?
    };
    if command.is_empty() || command[0].is_empty() {
        return Err(invalid("recorded argv is empty"));
    }
    let matcher = match quoted(field(&fields, "matcher")?)? {
        "cargo" => Matcher::Cargo,
        "npm-test" => Matcher::NpmTest,
        "git-diff" => Matcher::GitDiff,
        "search" => Matcher::Search,
        "passthrough" => Matcher::Passthrough,
        _ => return Err(invalid("unknown recorded matcher")),
    };
    let code_text = field(&fields, "exit_code")?;
    unsigned(code_text.strip_prefix('-').unwrap_or(code_text))?;
    let exit_code = code_text
        .parse::<i32>()
        .map_err(|_| invalid("invalid exit code"))?;
    let failed = boolean(field(&fields, "failed")?)?;
    if failed != (exit_code != 0) {
        return Err(invalid("recorded exit status and failure context disagree"));
    }
    let max_line_chars = match field(&fields, "max_line_chars")? {
        "null" => None,
        value => {
            let value =
                usize::try_from(unsigned(value)?).map_err(|_| invalid("line limit overflow"))?;
            if value == 0 {
                return Err(invalid("line limit must be positive"));
            }
            Some(value)
        }
    };
    let length_fields = [
        "stdout_raw_bytes",
        "stderr_raw_bytes",
        "stdout_filtered_bytes",
        "stderr_filtered_bytes",
    ];
    let mut raw = [Vec::new(), Vec::new()];
    for (index, name) in FILES.into_iter().enumerate() {
        let expected = unsigned(field(&fields, length_fields[index])?)?;
        let mut file = regular_file(&directory.join(name))?;
        if file.metadata()?.len() != expected {
            return Err(invalid("record stream length does not match metadata"));
        }
        if index < 2 {
            if expected > max_buffer as u64 {
                return Err(invalid("record stream exceeds replay buffer limit"));
            }
            Read::by_ref(&mut file)
                .take((max_buffer as u64).saturating_add(1))
                .read_to_end(&mut raw[index])?;
            if raw[index].len() as u64 != expected {
                return Err(invalid("record stream changed while reading"));
            }
        }
    }
    let [stdout, stderr] = raw;
    Ok(Replay {
        command,
        matcher,
        exit_code,
        failed,
        max_line_chars,
        stdout,
        stderr,
    })
}

fn create_private(path: &Path) -> io::Result<File> {
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    options.open(path)
}

fn regular_file(path: &Path) -> io::Result<File> {
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        return Err(invalid(
            "record streams and metadata must be ordinary files",
        ));
    }
    File::open(path)
}

fn invalid(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

// This is deliberately not a general JSON parser. The versioned flat schema
// has one field per line, ASCII strings, hex argv, and only scalar values.
// Noncanonical structures, duplicate/unknown fields, escapes, and extra data
// fail closed; Python and other JSON readers can inspect the emitted metadata.
fn parse_fields(text: &str) -> io::Result<BTreeMap<&str, &str>> {
    let lines: Vec<_> = text.trim().lines().collect();
    if lines.first().map(|line| line.trim()) != Some("{")
        || lines.last().map(|line| line.trim()) != Some("}")
    {
        return Err(invalid("invalid record metadata structure"));
    }
    let mut result = BTreeMap::new();
    for (index, original) in lines[1..lines.len() - 1].iter().enumerate() {
        let line = original.trim();
        let line = if index + 3 < lines.len() {
            line.strip_suffix(',')
                .ok_or_else(|| invalid("missing metadata separator"))?
        } else {
            line
        };
        let (key, value) = line
            .split_once(':')
            .ok_or_else(|| invalid("invalid metadata field"))?;
        if result.insert(quoted(key.trim())?, value.trim()).is_some() {
            return Err(invalid("duplicate metadata field"));
        }
    }
    let names = [
        "schema_version",
        "complete",
        "tool_version",
        "argv_encoding",
        "argv_hex",
        "matcher",
        "exit_code",
        "failed",
        "cancelled",
        "stdout_spilled",
        "stderr_spilled",
        "max_line_chars",
        "stdout_raw_bytes",
        "stderr_raw_bytes",
        "stdout_filtered_bytes",
        "stderr_filtered_bytes",
    ];
    if result.len() != names.len() || names.iter().any(|name| !result.contains_key(name)) {
        return Err(invalid("missing or unknown record metadata field"));
    }
    Ok(result)
}

fn field<'a>(fields: &BTreeMap<&str, &'a str>, name: &str) -> io::Result<&'a str> {
    fields
        .get(name)
        .copied()
        .ok_or_else(|| invalid("missing record metadata field"))
}

fn quoted(value: &str) -> io::Result<&str> {
    let value = value
        .strip_prefix('"')
        .and_then(|value| value.strip_suffix('"'))
        .ok_or_else(|| invalid("invalid metadata string"))?;
    if value
        .bytes()
        .any(|byte| !(0x20..=0x7e).contains(&byte) || matches!(byte, b'"' | b'\\'))
    {
        return Err(invalid("unsupported metadata string encoding"));
    }
    Ok(value)
}

fn boolean(value: &str) -> io::Result<bool> {
    match value {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => Err(invalid("invalid metadata boolean")),
    }
}

fn unsigned(value: &str) -> io::Result<u64> {
    if value.is_empty()
        || !value.bytes().all(|byte| byte.is_ascii_digit())
        || (value.len() > 1 && value.starts_with('0'))
    {
        return Err(invalid("invalid metadata number"));
    }
    value
        .parse()
        .map_err(|_| invalid("metadata number overflow"))
}

fn encoding() -> &'static str {
    if cfg!(unix) {
        "unix-bytes-hex"
    } else {
        "windows-utf16le-hex"
    }
}

fn encode_arg(value: &OsStr) -> io::Result<String> {
    #[cfg(unix)]
    let bytes = {
        use std::os::unix::ffi::OsStrExt;
        value.as_bytes().to_vec()
    };
    #[cfg(windows)]
    let bytes = {
        use std::os::windows::ffi::OsStrExt;
        value
            .encode_wide()
            .flat_map(u16::to_le_bytes)
            .collect::<Vec<_>>()
    };
    #[cfg(not(any(unix, windows)))]
    return Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "argv recording is unsupported on this platform",
    ));
    #[cfg(any(unix, windows))]
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

fn decode_arg(value: &str) -> io::Result<OsString> {
    if value.len() % 2 != 0 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(invalid("invalid argv hex encoding"));
    }
    let bytes = value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect::<Vec<_>>();
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStringExt;
        Ok(OsString::from_vec(bytes))
    }
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStringExt;
        if bytes.len() % 2 != 0 {
            return Err(invalid("invalid UTF-16 argv length"));
        }
        Ok(OsString::from_wide(
            &bytes
                .chunks_exact(2)
                .map(|pair| u16::from_le_bytes([pair[0], pair[1]]))
                .collect::<Vec<_>>(),
        ))
    }
    #[cfg(not(any(unix, windows)))]
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "argv replay is unsupported on this platform",
    ))
}
