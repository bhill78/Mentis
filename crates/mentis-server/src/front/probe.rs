//! A stop at a named line of the tail, a trace of each answer, and a scripted limit on a first write,
//! in a test build alone (`R3-mirror.md`, section 8). **Without the `tail-probe` feature every one of
//! these is nothing,** and no release build has it.

#[cfg(feature = "tail-probe")]
mod on {
    use std::io::Write as _;
    use std::path::{Path, PathBuf};
    use std::sync::OnceLock;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::Duration;

    static NEXT: AtomicU64 = AtomicU64::new(1);

    /// Where a test talks to this front, from `MENTIS_TAIL_DIR`.
    fn dir() -> Option<&'static Path> {
        static DIR: OnceLock<Option<PathBuf>> = OnceLock::new();
        DIR.get_or_init(|| std::env::var_os("MENTIS_TAIL_DIR").map(PathBuf::from))
            .as_deref()
    }

    /// The clock `FENCE` relies on: raw, so a trace can be compared with a Python's.
    #[cfg(windows)]
    fn clock() -> i64 {
        let mut now = 0;
        // SAFETY: writes one i64, which is here.
        unsafe { windows_sys::Win32::System::Performance::QueryPerformanceCounter(&mut now) };
        now
    }

    #[cfg(not(windows))]
    fn clock() -> i64 {
        let mut now = libc::timespec {
            tv_sec: 0,
            tv_nsec: 0,
        };
        // SAFETY: writes one timespec, which is here.
        unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut now) };
        i64::from(now.tv_sec) * 1_000_000_000 + i64::from(now.tv_nsec)
    }

    pub fn begin() -> u64 {
        NEXT.fetch_add(1, Ordering::SeqCst)
    }

    pub fn trace(id: u64, event: &str) {
        let Some(dir) = dir() else {
            return;
        };
        let line = format!(
            "{{\"id\": {id}, \"event\": \"{event}\", \"at\": {}}}\n",
            clock()
        );
        if let Ok(mut file) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(dir.join("trace.jsonl"))
        {
            let _ = file.write_all(line.as_bytes());
        }
    }

    /// A test arms a stop by making `stop-<line>`. The first tail to reach that line takes it, says
    /// so with `stopped-<line>`, and waits for `go-<line>`, on this thread, holding what it holds.
    pub fn stop(line: &str) {
        let Some(dir) = dir() else {
            return;
        };
        if std::fs::remove_file(dir.join(format!("stop-{line}"))).is_err() {
            return;
        }
        let go = dir.join(format!("go-{line}"));
        let _ = std::fs::write(dir.join(format!("stopped-{line}")), b"");
        while !go.exists() {
            std::thread::sleep(Duration::from_millis(2));
        }
        let _ = std::fs::remove_file(go);
    }

    /// What a `try_write` is offered. A test limits one write by making `limit`, holding a number
    /// of bytes, and every write by making `limit-each`. Windows takes the whole of one write if its
    /// send buffer isn't already full, so without this a large answer is never part-accepted there.
    pub fn limited(bytes: &[u8]) -> &[u8] {
        let Some(dir) = dir() else {
            return bytes;
        };
        let once = dir.join("limit");
        let text = match std::fs::read_to_string(&once) {
            Ok(text) => {
                let _ = std::fs::remove_file(once);
                text
            }
            Err(_) => std::fs::read_to_string(dir.join("limit-each")).unwrap_or_default(),
        };
        match text.trim().parse::<usize>() {
            Ok(most) => &bytes[..most.min(bytes.len())],
            Err(_) => bytes,
        }
    }

    /// A shortened `SEND_BOUND`, from `MENTIS_TAIL_SEND_BOUND_MS`.
    pub fn send_bound(bound: Duration) -> Duration {
        std::env::var("MENTIS_TAIL_SEND_BOUND_MS")
            .ok()
            .and_then(|text| text.parse().ok())
            .map_or(bound, Duration::from_millis)
    }
}

#[cfg(feature = "tail-probe")]
pub use on::*;

#[cfg(not(feature = "tail-probe"))]
mod off {
    use std::time::Duration;

    #[inline]
    pub fn begin() -> u64 {
        0
    }

    #[inline]
    pub fn trace(_id: u64, _event: &str) {}

    #[inline]
    pub fn stop(_line: &str) {}

    #[inline]
    pub fn limited(bytes: &[u8]) -> &[u8] {
        bytes
    }

    #[inline]
    pub fn send_bound(bound: Duration) -> Duration {
        bound
    }
}

#[cfg(not(feature = "tail-probe"))]
pub use off::*;
