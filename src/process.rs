//! Supervise buffered commands without making cancellation depend on pipe EOF.
use std::io;
use std::process::{Child, ChildStderr, ChildStdout, Command, ExitStatus};
use std::sync::atomic::{AtomicI32, Ordering};
use std::thread;
use std::time::{Duration, Instant};

const GRACE: Duration = Duration::from_millis(500);
const DRAIN: Duration = Duration::from_millis(100);

pub struct Process {
    child: Child,
    signals: platform::Signals,
    status: Option<ExitStatus>,
    stopping: Option<Instant>,
    killed: bool,
    io_exit: i32,
}

impl Process {
    pub fn spawn(command: &mut Command) -> io::Result<Self> {
        // Register before spawn: cancellation during startup must not orphan a child.
        let signals = platform::Signals::install()?;
        platform::configure(command);
        let child = command.spawn()?;
        Ok(Self {
            child,
            signals,
            status: None,
            stopping: None,
            killed: false,
            io_exit: 0,
        })
    }

    pub fn stdout(&mut self) -> ChildStdout {
        self.child.stdout.take().expect("piped stdout")
    }

    pub fn stderr(&mut self) -> ChildStderr {
        self.child.stderr.take().expect("piped stderr")
    }

    /// Returns false if cancellation's drain deadline expires. In that case
    /// callers must detach unfinished IO threads, not block on joining them.
    /// The CLI exits immediately afterward, closing its remaining descriptors.
    pub fn wait_until(
        &mut self,
        finished: impl Fn() -> bool,
        io_exit: &AtomicI32,
    ) -> io::Result<bool> {
        loop {
            if self.status.is_none() {
                self.status = self.child.try_wait()?;
            }
            // Observe thread completion before loading its error notification.
            // Otherwise a just-finished writer could be mistaken for success.
            let done = finished();
            self.io_exit = io_exit.load(Ordering::Relaxed);
            if self.stopping.is_none() && (self.signals.received().is_some() || self.io_exit != 0) {
                self.stopping = Some(Instant::now());
                self.terminate(self.signals.received().unwrap_or(15));
            }
            if let Some(started) = self.stopping {
                if !self.killed && started.elapsed() >= GRACE {
                    // The leader may have exited while descendants still run.
                    // Always target the entire original process group.
                    self.terminate(9);
                    self.killed = true;
                }
                if self.killed
                    && ((done && self.status.is_some()) || started.elapsed() >= GRACE + DRAIN)
                {
                    return Ok(done);
                }
            } else if done && self.status.is_some() {
                return Ok(true);
            }
            thread::sleep(Duration::from_millis(5));
        }
    }

    pub fn cancelled(&self) -> bool {
        self.signals.received().is_some()
    }

    pub fn exit_code(&self) -> i32 {
        if let Some(signal) = self.signals.received() {
            128 + signal
        } else if self.io_exit != 0 {
            self.io_exit
        } else {
            self.status.map(status_code).unwrap_or(1)
        }
    }

    pub fn failed(&self) -> bool {
        self.status.map_or(true, |status| !status.success())
    }

    fn terminate(&mut self, signal: i32) {
        platform::terminate_group(self.child.id(), signal);
        if signal == 9 && self.status.is_none() {
            // Defensive fallback if a child has changed its process group.
            let _ = self.child.kill();
        }
    }
}

impl Drop for Process {
    fn drop(&mut self) {
        // Error paths must also stop and reap the direct child. A cancelled
        // group was already killed by wait_until, so its descendants are covered.
        if self.status.is_none() {
            self.terminate(9);
            let _ = self.child.wait();
        }
    }
}

fn status_code(status: ExitStatus) -> i32 {
    if let Some(code) = status.code() {
        return code;
    }
    #[cfg(unix)]
    {
        use std::os::unix::process::ExitStatusExt;
        128 + status.signal().unwrap_or(1)
    }
    #[cfg(not(unix))]
    {
        1
    }
}

#[cfg(unix)]
mod platform {
    use super::*;
    use std::os::raw::c_int;
    use std::os::unix::process::CommandExt;

    static RECEIVED: AtomicI32 = AtomicI32::new(0);

    // macOS and glibc Linux export the BSD signal ABI: a handler-sized value,
    // persistent handlers, and restartable syscalls. Avoid platform-specific
    // sigaction struct layouts. These are the platforms exercised by CI.
    extern "C" {
        fn signal(number: c_int, handler: usize) -> usize;
        fn kill(pid: c_int, number: c_int) -> c_int;
    }

    extern "C" fn record_signal(number: c_int) {
        // Lock-free on supported targets; no allocation, locking, or IO in a handler.
        let _ = RECEIVED.compare_exchange(0, number, Ordering::Relaxed, Ordering::Relaxed);
    }

    pub struct Signals {
        interrupt: usize,
        terminate: usize,
    }

    impl Signals {
        pub fn install() -> io::Result<Self> {
            let handler = record_signal as *const () as usize;
            // SAFETY: these are the supported platforms' SIGINT/SIGTERM numbers.
            // The callback uses only a lock-free atomic and has the C ABI.
            let interrupt = unsafe { signal(2, handler) };
            if interrupt == usize::MAX {
                return Err(io::Error::last_os_error());
            }
            let terminate = unsafe { signal(15, handler) };
            if terminate == usize::MAX {
                let error = io::Error::last_os_error();
                // SAFETY: restore the handler value returned by signal().
                unsafe { signal(2, interrupt) };
                return Err(error);
            }
            Ok(Self {
                interrupt,
                terminate,
            })
        }

        pub fn received(&self) -> Option<i32> {
            match RECEIVED.load(Ordering::Relaxed) {
                0 => None,
                signal => Some(signal),
            }
        }
    }

    impl Drop for Signals {
        fn drop(&mut self) {
            // SAFETY: restore exactly the disposition values returned at installation.
            unsafe {
                signal(2, self.interrupt);
                signal(15, self.terminate);
            }
        }
    }

    pub fn configure(command: &mut Command) {
        command.process_group(0);
    }

    pub fn terminate_group(pid: u32, number: i32) {
        if let Ok(pid) = i32::try_from(pid) {
            if pid > 1 {
                // SAFETY: a negative child PID targets its dedicated process group,
                // never mini's own group. ESRCH after normal termination is harmless.
                unsafe { kill(-pid, number) };
            }
        }
    }
}

#[cfg(not(unix))]
mod platform {
    use super::*;
    pub struct Signals;
    impl Signals {
        pub fn install() -> io::Result<Self> {
            Ok(Self)
        }
        pub fn received(&self) -> Option<i32> {
            None
        }
    }
    pub fn configure(_: &mut Command) {}
    pub fn terminate_group(_: u32, _: i32) {}
}
