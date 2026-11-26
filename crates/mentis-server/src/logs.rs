//! `front.log` and `python.log`, bounded: `contracts/launcher.md`, "Logs".
//!
//! Each process's output goes through a pipe to a small `mentis-launch log-pipe` process, the only
//! writer of its file, which starts a new file once the current one reaches [`MOST_LOG_BYTES`]
//! and keeps [`OLD_LOGS_KEPT`] old ones (`front.log.1` the newest). It rotates between lines,
//! so no line is split or lost, and it never stops reading: a file it can't write drops what it
//! was given rather than leave the server blocked on a full pipe. It ends when the last process
//! that can write to its pipe has ended. It watches nothing and restarts nothing.

use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};

/// A log reaching this size is rotated at its next line's end.
pub const MOST_LOG_BYTES: u64 = 20 * 1024 * 1024;
/// How many rotated files are kept beside the current one: `.1` (newest) to this.
pub const OLD_LOGS_KEPT: u32 = 3;

/// A log file of bounded size. Every write is taken, whether or not it reaches the file.
pub struct Rotating {
    path: PathBuf,
    file: Option<File>,
    size: u64,
    most: u64,
    keep: u32,
    /// The last byte written ended a line, so a rotation now splits none.
    at_line_start: bool,
}

impl Rotating {
    pub fn open(path: &Path, most: u64, keep: u32) -> io::Result<Self> {
        let file = append_to(path)?;
        let size = file.metadata().map(|meta| meta.len()).unwrap_or(0);
        Ok(Self {
            path: path.to_owned(),
            file: Some(file),
            size,
            most,
            keep,
            at_line_start: true,
        })
    }

    /// Writes all of `bytes`, rotating first at a line's end once the file has reached its size.
    /// A line that never ends is cut at twice the size, so the bound holds whatever is written.
    pub fn write(&mut self, mut bytes: &[u8]) {
        while !bytes.is_empty() {
            if self.size >= self.most {
                if self.at_line_start || self.size >= self.most.saturating_mul(2) {
                    self.rotate();
                } else if let Some(end) = bytes.iter().position(|byte| *byte == b'\n') {
                    self.put(&bytes[..=end]);
                    bytes = &bytes[end + 1..];
                    self.rotate();
                    continue;
                }
            }
            self.put(bytes);
            return;
        }
    }

    fn put(&mut self, bytes: &[u8]) {
        if bytes.is_empty() {
            return;
        }
        if self.file.is_none() {
            self.file = append_to(&self.path).ok();
        }
        if let Some(file) = &mut self.file
            && file.write_all(bytes).is_err()
        {
            // Tried again with the next write, on a file opened again.
            self.file = None;
        }
        self.size += bytes.len() as u64;
        self.at_line_start = bytes.last() == Some(&b'\n');
    }

    /// `log` to `log.1`, each older one up by one, the oldest past `keep` gone, and a new `log`.
    /// If `log` can't be renamed (something holds it open without sharing delete), it is copied to
    /// `log.1` and emptied instead.
    fn rotate(&mut self) {
        self.file = None;
        if self.keep == 0 {
            let _ = OpenOptions::new()
                .write(true)
                .truncate(true)
                .open(&self.path);
        } else {
            for at in (1..self.keep).rev() {
                let from = numbered(&self.path, at);
                if from.exists() {
                    let _ = fs::rename(&from, numbered(&self.path, at + 1));
                }
            }
            let first = numbered(&self.path, 1);
            if fs::rename(&self.path, &first).is_err() {
                let _ = fs::copy(&self.path, &first);
                let _ = OpenOptions::new()
                    .write(true)
                    .truncate(true)
                    .open(&self.path);
            }
        }
        self.file = append_to(&self.path).ok();
        self.size = self
            .file
            .as_ref()
            .and_then(|file| file.metadata().ok())
            .map_or(0, |meta| meta.len());
        self.at_line_start = true;
    }
}

fn append_to(path: &Path) -> io::Result<File> {
    OpenOptions::new().create(true).append(true).open(path)
}

/// `log.<at>`.
pub fn numbered(path: &Path, at: u32) -> PathBuf {
    let mut name = path.as_os_str().to_owned();
    name.push(format!(".{at}"));
    PathBuf::from(name)
}

/// Everything `input` says, into `log`, until it ends.
pub fn pipe(mut input: impl Read, log: &mut Rotating) {
    let mut chunk = vec![0; 64 * 1024];
    loop {
        match input.read(&mut chunk) {
            Ok(0) => return,
            Ok(got) => log.write(&chunk[..got]),
            Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
            Err(_) => return,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("mentis-logs-{}-{name}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn size(path: &Path) -> u64 {
        fs::metadata(path).map_or(0, |meta| meta.len())
    }

    #[test]
    fn rotation_caps_the_size_keeps_n_old_files_and_loses_no_line() {
        let dir = dir("cap");
        let log = dir.join("front.log");
        let mut rotating = Rotating::open(&log, 1000, 3).unwrap();
        let mut written = Vec::new();
        for at in 0..400 {
            let line = format!("line {at:05} {}\n", "x".repeat(at % 37));
            written.push(line.clone());
            // In pieces, as a pipe gives it.
            let (head, tail) = line.as_bytes().split_at(line.len() / 2);
            rotating.write(head);
            rotating.write(tail);
        }
        drop(rotating);
        assert!(!numbered(&log, 4).exists(), "only three old files");
        let mut kept = String::new();
        for at in (1..=3).rev() {
            let old = numbered(&log, at);
            assert!(
                size(&old) >= 1000 && size(&old) < 1000 + 64,
                "{}",
                size(&old)
            );
            kept.push_str(&fs::read_to_string(old).unwrap());
        }
        assert!(size(&log) < 1000 + 64);
        kept.push_str(&fs::read_to_string(&log).unwrap());
        // Every line whole, in order, and the newest of them all there.
        let all: String = written.concat();
        assert!(all.ends_with(&kept), "lines lost or split");
        for line in kept.lines() {
            assert!(line.starts_with("line "), "{line:?}");
        }
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_line_that_never_ends_is_still_bounded() {
        let dir = dir("endless");
        let log = dir.join("python.log");
        let mut rotating = Rotating::open(&log, 100, 2).unwrap();
        for _ in 0..100 {
            rotating.write(&[b'y'; 50]);
        }
        drop(rotating);
        for path in [log.clone(), numbered(&log, 1), numbered(&log, 2)] {
            assert!(size(&path) <= 250, "{}: {}", path.display(), size(&path));
        }
        assert!(!numbered(&log, 3).exists());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn what_was_there_counts_and_a_pipe_is_read_to_its_end() {
        let dir = dir("pipe");
        let log = dir.join("front.log");
        let before = "x".repeat(999) + "\n";
        fs::write(&log, &before).unwrap();
        let mut rotating = Rotating::open(&log, 1000, 3).unwrap();
        pipe(&b"one\ntwo\n"[..], &mut rotating);
        drop(rotating);
        assert_eq!(fs::read_to_string(&log).unwrap(), "one\ntwo\n");
        assert_eq!(fs::read_to_string(numbered(&log, 1)).unwrap(), before);
        let _ = fs::remove_dir_all(&dir);
    }
}
