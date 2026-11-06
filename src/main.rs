use minifycli::{minify, select_matcher, Matcher};
use std::env;
use std::ffi::OsString;
use std::fs::File;
use std::io::{self, Read, Write};
use std::path::PathBuf;
#[cfg(not(unix))]
use std::process::ExitStatus;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicI32, Ordering};
use std::sync::Arc;
use std::thread;

mod process;
mod recording;
const HELP: &str = "mini — terminal output compression for coding agents

Usage: mini [OPTIONS] [--] COMMAND [ARGS...]
       mini --replay DIR [--stats] [--max-buffer N]

Options (before COMMAND):
  --stats              Print actual byte counts to stderr (not with --raw)
  --raw                Bypass compression; inherit live terminal streams
  --record DIR         Save raw/filtered child streams locally in a NEW directory
  --replay DIR         Refilter a complete record without executing its command
  --max-buffer N       Per-stream capture cap in bytes (default: 4194304)
  --max-line-chars N   Opt-in search match clipping; adds an omission marker
  -h, --help           Show this help
  -V, --version        Show version

Examples:
  mini cargo test
  mini --stats git diff
  mini rg -n TODO src
  mini --raw npm test -- --watch

Arguments, stdin, cwd, environment, and child exit codes are preserved.
Known commands are buffered until exit. Unknown commands pass through live.
Use --raw for scripts, exact patches, interactive tools, and machine output.
No shell expansion is performed; use an explicit shell for pipelines.
Recording is opt-in and can contain private output or sensitive arguments.
Raw passthrough and recording cannot be combined.
";

#[derive(Debug)]
struct Options {
    command: Vec<OsString>,
    stats: bool,
    raw: bool,
    max_buffer: usize,
    max_line_chars: Option<usize>,
    record: Option<PathBuf>,
}

enum Action {
    Run(Options),
    Replay {
        directory: PathBuf,
        stats: bool,
        max_buffer: usize,
    },
    Help,
    Version,
}

fn parse(args: impl IntoIterator<Item = OsString>) -> Result<Action, String> {
    let mut args = args.into_iter().peekable();
    let mut options = Options {
        command: Vec::new(),
        stats: false,
        raw: false,
        max_buffer: 4 * 1024 * 1024,
        max_line_chars: None,
        record: None,
    };
    let mut replay = None;
    while let Some(arg) = args.next() {
        match arg.to_str() {
            Some("-h" | "--help") => return Ok(Action::Help),
            Some("-V" | "--version") => return Ok(Action::Version),
            Some("--stats") => options.stats = true,
            Some("--raw") => options.raw = true,
            Some("--record" | "--replay") => {
                let name = arg.to_string_lossy();
                let directory = args
                    .next()
                    .ok_or_else(|| format!("{name} requires a directory"))?;
                let target = if name == "--record" {
                    &mut options.record
                } else {
                    &mut replay
                };
                if target.replace(PathBuf::from(directory)).is_some() {
                    return Err(format!("{name} can only be supplied once"));
                }
            }
            Some("--max-buffer" | "--max-line-chars") => {
                let name = arg.to_string_lossy();
                let value = args
                    .next()
                    .ok_or_else(|| format!("{name} requires a positive integer"))?;
                let number = value
                    .to_str()
                    .and_then(|s| s.parse::<usize>().ok())
                    .filter(|n| *n > 0)
                    .ok_or_else(|| format!("{name} requires a positive integer"))?;
                if name == "--max-buffer" {
                    options.max_buffer = number;
                } else {
                    options.max_line_chars = Some(number);
                }
            }
            Some("--") => {
                options.command.extend(args);
                break;
            }
            Some(s) if s.starts_with('-') => return Err(format!("unknown option: {s}")),
            _ => {
                options.command.push(arg);
                options.command.extend(args);
                break;
            }
        }
    }
    if let Some(directory) = replay {
        if !options.command.is_empty()
            || options.raw
            || options.record.is_some()
            || options.max_line_chars.is_some()
        {
            return Err(
                "--replay accepts no command, --raw, --record, or line-clipping override".into(),
            );
        }
        return Ok(Action::Replay {
            directory,
            stats: options.stats,
            max_buffer: options.max_buffer,
        });
    }
    if options.command.is_empty() {
        return Err("a command is required (see mini --help)".into());
    }
    if options.raw && options.stats {
        return Err("--raw and --stats cannot be combined; --raw inherits terminal streams".into());
    }
    if options.raw && options.record.is_some() {
        return Err(
            "--raw and --record cannot be combined; --raw inherits terminal streams".into(),
        );
    }
    Ok(Action::Run(options))
}

struct Captured {
    bytes: Vec<u8>,
    total: u64,
    spilled: bool,
}

/// Drain both pipes concurrently. If a stream exceeds the cap, emit its
/// original buffered prefix and copy remaining bytes without transformation.
fn capture(
    mut reader: impl Read,
    mut writer: impl Write,
    limit: usize,
    mut raw_record: Option<File>,
) -> io::Result<Captured> {
    let mut captured = Captured {
        bytes: Vec::new(),
        total: 0,
        spilled: false,
    };
    let mut chunk = [0; 8192];
    loop {
        let count = match reader.read(&mut chunk) {
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            result => result?,
        };
        if count == 0 {
            break;
        }
        captured.total += count as u64;
        if let Some(file) = raw_record.as_mut() {
            file.write_all(&chunk[..count])?;
        }
        if !captured.spilled && count <= limit.saturating_sub(captured.bytes.len()) {
            captured.bytes.extend_from_slice(&chunk[..count]);
        } else {
            if !captured.spilled {
                writer.write_all(&captured.bytes)?;
                captured.bytes = Vec::new();
                captured.spilled = true;
            }
            writer.write_all(&chunk[..count])?;
            writer.flush()?;
        }
    }
    if let Some(file) = raw_record.as_mut() {
        file.flush()?;
    }
    Ok(captured)
}

fn with_record<W: Write + Send + 'static>(
    writer: W,
    record: Option<File>,
) -> Box<dyn Write + Send> {
    match record {
        Some(file) => Box::new(recording::TeeWriter::new(writer, file)),
        None => Box::new(writer),
    }
}

#[cfg(not(unix))]
fn code(status: ExitStatus) -> i32 {
    status.code().unwrap_or(1)
}

fn passthrough(mut command: Command) -> io::Result<i32> {
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        Err(command.exec())
    }
    #[cfg(not(unix))]
    {
        command.status().map(code)
    }
}

fn run(options: Options) -> io::Result<i32> {
    let matcher = if options.raw {
        Matcher::Passthrough
    } else {
        select_matcher(&options.command)
    };
    let mut command = Command::new(&options.command[0]);
    command.args(&options.command[1..]);
    if matcher == Matcher::Passthrough && !options.stats && options.record.is_none() {
        return passthrough(command);
    }
    let mut record = options
        .record
        .as_deref()
        .map(recording::Record::create)
        .transpose()?;
    let mut raw_files = [None, None];
    let mut filtered_files = [None, None];
    if let Some(record) = record.as_mut() {
        for (index, stream) in [recording::Stream::Stdout, recording::Stream::Stderr]
            .into_iter()
            .enumerate()
        {
            raw_files[index] = Some(record.take_raw(stream)?);
            filtered_files[index] = Some(record.take_filtered(stream)?);
        }
    }
    command
        .stdin(Stdio::inherit())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = process::Process::spawn(&mut command)?;
    let stdout = child.stdout();
    let stderr = child.stderr();
    let limit = options.max_buffer;
    let io_exit = Arc::new(AtomicI32::new(0));
    let out_error = Arc::clone(&io_exit);
    let err_error = Arc::clone(&io_exit);
    let [out_raw, err_raw] = raw_files;
    let out_sink = with_record(
        io::stdout(),
        filtered_files[0]
            .as_ref()
            .map(File::try_clone)
            .transpose()?,
    );
    let err_sink = with_record(
        io::stderr(),
        filtered_files[1]
            .as_ref()
            .map(File::try_clone)
            .transpose()?,
    );
    let out_thread =
        thread::spawn(move || report_io(capture(stdout, out_sink, limit, out_raw), &out_error));
    let err_thread =
        thread::spawn(move || report_io(capture(stderr, err_sink, limit, err_raw), &err_error));
    if !child.wait_until(
        || out_thread.is_finished() && err_thread.is_finished(),
        &io_exit,
    )? {
        // Dropping a JoinHandle detaches it. Process exit closes blocked pipes;
        // joining here could hang forever on a descendant or a stalled consumer.
        return Ok(child.exit_code(&io_exit));
    }
    if io_exit.load(Ordering::Relaxed) != 0 {
        return Ok(child.exit_code(&io_exit));
    }
    let stdout = out_thread
        .join()
        .map_err(|_| io::Error::other("stdout reader panicked"))??;
    let stderr = err_thread
        .join()
        .map_err(|_| io::Error::other("stderr reader panicked"))??;
    let mut input_bytes = 0;
    let mut output_bytes = 0;
    let mut spills = 0;
    let spilled = [stdout.spilled, stderr.spilled];
    let mut outputs = [Vec::new(), Vec::new()];
    for (index, captured) in [stdout, stderr].into_iter().enumerate() {
        input_bytes += captured.total;
        if captured.spilled {
            output_bytes += captured.total;
            spills += 1;
            continue;
        }
        // Search errors are not match data. Test runners may write their reports
        // to either stream. Never group or clip stderr for grep/rg or git.
        let stream_matcher = if child.cancelled()
            || (index == 1 && matches!(matcher, Matcher::Search | Matcher::GitDiff))
        {
            Matcher::Passthrough
        } else {
            matcher
        };
        let output = minify(
            &captured.bytes,
            stream_matcher,
            child.failed(),
            options.max_line_chars,
        );
        output_bytes += output.len() as u64;
        outputs[index] = output;
    }
    let stats = if options.stats && !child.cancelled() {
        let reduction = if input_bytes == 0 {
            0.0
        } else {
            100.0 * (input_bytes - output_bytes) as f64 / input_bytes as f64
        };
        Some(format!(
            "[mini] matcher={} input={}B output={}B saved={:.1}% passthrough_streams={}\n",
            matcher.name(),
            input_bytes,
            output_bytes,
            reduction,
            spills
        ))
    } else {
        None
    };
    let [stdout, stderr] = outputs;
    let [out_record, err_record] = filtered_files;
    let out_error = Arc::clone(&io_exit);
    let err_error = Arc::clone(&io_exit);
    let out_thread = thread::spawn(move || {
        let mut writer = with_record(io::stdout(), out_record);
        report_io(
            writer.write_all(&stdout).and_then(|_| writer.flush()),
            &out_error,
        )
    });
    let err_thread = thread::spawn(move || {
        let mut writer = with_record(io::stderr(), err_record);
        let result = writer
            .write_all(&stderr)
            .and_then(|_| writer.flush())
            .and_then(|_| {
                if let Some(stats) = stats {
                    io::stderr().write_all(stats.as_bytes())
                } else {
                    Ok(())
                }
            });
        report_io(result, &err_error)
    });
    if child.wait_until(
        || out_thread.is_finished() && err_thread.is_finished(),
        &io_exit,
    )? {
        if io_exit.load(Ordering::Relaxed) != 0 {
            return Ok(child.exit_code(&io_exit));
        }
        out_thread
            .join()
            .map_err(|_| io::Error::other("stdout writer panicked"))??;
        err_thread
            .join()
            .map_err(|_| io::Error::other("stderr writer panicked"))??;
        if let Some(record) = record {
            let exit_code = child.exit_code(&io_exit);
            record.finish(recording::Metadata {
                command: options.command,
                matcher,
                exit_code,
                failed: exit_code != 0,
                cancelled: child.cancelled(),
                spilled,
                max_line_chars: options.max_line_chars,
                complete: !child.cancelled() && !spilled.into_iter().any(|value| value),
            })?;
        }
    }
    Ok(child.exit_code(&io_exit))
}

fn replay(directory: PathBuf, stats: bool, max_buffer: usize) -> io::Result<i32> {
    let captured = recording::load_replay(&directory, max_buffer)?;
    let [stdout, stderr] = captured.render();
    io::stdout().write_all(&stdout)?;
    io::stderr().write_all(&stderr)?;
    if stats {
        let input = captured.stdout.len() + captured.stderr.len();
        let output = stdout.len() + stderr.len();
        let reduction = if input == 0 {
            0.0
        } else {
            100.0 * (input - output) as f64 / input as f64
        };
        writeln!(
            io::stderr(),
            "[mini] replay matcher={} recorded_matcher={} input={}B output={}B saved={:.1}%",
            select_matcher(&captured.command).name(),
            captured.matcher.name(),
            input,
            output,
            reduction
        )?;
    }
    Ok(captured.exit_code)
}

fn report_io<T>(result: io::Result<T>, exit: &AtomicI32) -> io::Result<T> {
    if let Err(error) = &result {
        let code = if error.kind() == io::ErrorKind::BrokenPipe {
            141
        } else {
            1
        };
        let _ = exit.compare_exchange(0, code, Ordering::Release, Ordering::Relaxed);
    }
    result
}

fn main() {
    let action = match parse(env::args_os().skip(1)) {
        Ok(action) => action,
        Err(error) => {
            let _ = writeln!(io::stderr(), "mini: {error}");
            std::process::exit(2);
        }
    };
    let result = match action {
        Action::Help => io::stdout().write_all(HELP.as_bytes()).map(|_| 0),
        Action::Version => writeln!(io::stdout(), "mini {}", env!("CARGO_PKG_VERSION")).map(|_| 0),
        Action::Run(options) => run(options),
        Action::Replay {
            directory,
            stats,
            max_buffer,
        } => replay(directory, stats, max_buffer),
    };
    let exit_code = match result {
        Ok(code) => code,
        Err(error) if error.kind() == io::ErrorKind::BrokenPipe => 141,
        Err(error) => {
            let _ = writeln!(io::stderr(), "mini: {error}");
            match error.kind() {
                io::ErrorKind::NotFound => 127,
                io::ErrorKind::PermissionDenied => 126,
                _ => 1,
            }
        }
    };
    std::process::exit(exit_code);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn spill_is_byte_exact_and_bounded() {
        let input = vec![b'x'; 20_000];
        let mut output = Vec::new();
        let result = capture(input.as_slice(), &mut output, 8, None).unwrap();
        assert!(result.spilled);
        assert!(result.bytes.is_empty());
        assert_eq!(result.total, 20_000);
        assert_eq!(output, input);
    }

    #[test]
    fn options_stop_at_command() {
        let Action::Run(options) =
            parse(["--stats", "npm", "test", "--help"].map(OsString::from)).unwrap()
        else {
            panic!()
        };
        assert_eq!(
            options.command,
            ["npm", "test", "--help"].map(OsString::from)
        );
        assert!(options.stats);
    }

    #[test]
    fn invalid_options_fail_before_execution() {
        for args in [
            vec![],
            vec!["--bad"],
            vec!["--max-buffer", "0"],
            vec!["--max-line-chars", "no"],
            vec!["--raw", "--stats", "cargo", "test"],
        ] {
            assert!(parse(args.into_iter().map(OsString::from)).is_err());
        }
    }
}
