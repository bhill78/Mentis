//! What the kernel says, for the mirror and its tail: Python's lock files, opened read-only and
//! never created, and the watch on Python's process. `docs/rust/R3-mirror.md`, section 4.
//!
//! The locks are `spine/brainlock.py:77-81`'s: `LockFileEx` on one byte at offset 0, and `flock` on
//! POSIX, without blocking. A lock dies with its handle.

use std::fs::File;
use std::io::{self, Read};
use std::path::Path;

/// The answer to a try for a shared lock.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Tried {
    Taken,
    /// Somebody holds it exclusive.
    Busy,
    /// No clear answer. Nothing can be said from this.
    Failed,
}

/// One of Python's files, read-only. Rust writes nothing to the Brain, and a shared lock on a
/// handle opened for reading is enough on both systems.
#[derive(Debug)]
pub struct BrainFile {
    file: File,
}

/// What a claim of this boot is: exactly its 32 bytes.
pub const CLAIM_SIZE: usize = 32;

impl BrainFile {
    /// Fails if it is missing: this never creates one.
    pub fn open(path: &Path) -> io::Result<BrainFile> {
        Ok(BrainFile {
            file: File::open(path)?,
        })
    }

    pub fn try_shared(&self) -> Tried {
        os::try_shared(&self.file)
    }

    pub fn unlock(&self) {
        os::unlock(&self.file);
    }

    /// Whether the whole file is these 32 bytes. A file of any other length isn't this boot.
    /// From offset 0, through a handle not read before.
    pub fn says(&self, boot: &str) -> io::Result<bool> {
        let mut got = Vec::with_capacity(CLAIM_SIZE + 1);
        (&self.file)
            .take(CLAIM_SIZE as u64 + 1)
            .read_to_end(&mut got)?;
        Ok(got == boot.as_bytes())
    }
}

/// A process's end, asked without blocking. Has no thread or timer, and nothing but the mirror may
/// read it (`contracts/launcher.md`, "R3: the watch and the claim").
pub trait Ended: Send + Sync {
    fn ended(&self) -> bool;
}

/// Solely to validate the lifetime of mirrored authorization state.
#[derive(Debug)]
pub struct ProcessWatch(os::Watch);

impl ProcessWatch {
    /// `None` is no watch, so nothing is `Held` and everything forwards.
    pub fn open(pid: u32) -> Option<ProcessWatch> {
        os::Watch::open(pid).map(ProcessWatch)
    }
}

impl Ended for ProcessWatch {
    fn ended(&self) -> bool {
        self.0.ended()
    }
}

#[cfg(windows)]
mod os {
    use std::fs::File;
    use std::os::windows::io::AsRawHandle;

    use windows_sys::Win32::Foundation::{
        CloseHandle, ERROR_IO_PENDING, ERROR_LOCK_VIOLATION, HANDLE, WAIT_TIMEOUT,
    };
    use windows_sys::Win32::Storage::FileSystem::{
        LOCKFILE_FAIL_IMMEDIATELY, LockFileEx, UnlockFileEx,
    };
    use windows_sys::Win32::System::IO::OVERLAPPED;
    use windows_sys::Win32::System::Threading::{
        OpenProcess, PROCESS_SYNCHRONIZE, WaitForSingleObject,
    };

    use super::Tried;

    pub(super) fn try_shared(file: &File) -> Tried {
        let handle = file.as_raw_handle() as HANDLE;
        // SAFETY: the handle is open for as long as `file` is, and the OVERLAPPED is zeroed (offset
        // 0, no event) and outlives this call, which with FAIL_IMMEDIATELY does not pend.
        let taken = unsafe {
            let mut at: OVERLAPPED = std::mem::zeroed();
            LockFileEx(handle, LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &mut at)
        };
        if taken != 0 {
            return Tried::Taken;
        }
        match std::io::Error::last_os_error()
            .raw_os_error()
            .map(|code| code as u32)
        {
            Some(ERROR_LOCK_VIOLATION | ERROR_IO_PENDING) => Tried::Busy,
            _ => Tried::Failed,
        }
    }

    pub(super) fn unlock(file: &File) {
        let handle = file.as_raw_handle() as HANDLE;
        // SAFETY: as above. A failure leaves the close that follows to release it.
        unsafe {
            let mut at: OVERLAPPED = std::mem::zeroed();
            UnlockFileEx(handle, 0, 1, 0, &mut at);
        }
    }

    #[derive(Debug)]
    pub(super) struct Watch(HANDLE);

    // SAFETY: a process handle is usable from any thread, and this only waits on it and closes it.
    unsafe impl Send for Watch {}
    // SAFETY: as above, and a zero-timeout wait changes nothing.
    unsafe impl Sync for Watch {}

    impl Watch {
        pub(super) fn open(pid: u32) -> Option<Watch> {
            // SAFETY: asks only to wait on it, and the handle is closed on drop.
            let process = unsafe { OpenProcess(PROCESS_SYNCHRONIZE, 0, pid) };
            (!process.is_null()).then_some(Watch(process))
        }

        /// A failed wait reads as ended, so a read forwards.
        pub(super) fn ended(&self) -> bool {
            // SAFETY: a handle opened above and not yet closed. A timeout of 0 doesn't block.
            unsafe { WaitForSingleObject(self.0, 0) != WAIT_TIMEOUT }
        }
    }

    impl Drop for Watch {
        fn drop(&mut self) {
            // SAFETY: as above, and closed once.
            unsafe { CloseHandle(self.0) };
        }
    }
}

#[cfg(unix)]
mod os {
    use std::fs::File;
    use std::os::fd::AsRawFd;

    use super::Tried;

    pub(super) fn try_shared(file: &File) -> Tried {
        // SAFETY: the descriptor is open for as long as `file` is.
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_SH | libc::LOCK_NB) } == 0 {
            return Tried::Taken;
        }
        match std::io::Error::last_os_error().raw_os_error() {
            Some(libc::EWOULDBLOCK | libc::EACCES) => Tried::Busy,
            _ => Tried::Failed,
        }
    }

    pub(super) fn unlock(file: &File) {
        // SAFETY: as above. A failure leaves the close that follows to release it.
        unsafe {
            libc::flock(file.as_raw_fd(), libc::LOCK_UN);
        }
    }

    #[derive(Debug)]
    pub(super) struct Watch(Option<libc::c_int>);

    impl Watch {
        #[cfg(target_os = "linux")]
        pub(super) fn open(pid: u32) -> Option<Watch> {
            // SAFETY: a system call that takes two integers and returns a descriptor or -1.
            let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, pid as libc::pid_t, 0) };
            (fd >= 0).then_some(Watch(Some(fd as libc::c_int)))
        }

        /// No pidfd here, so no watch, and everything forwards.
        #[cfg(not(target_os = "linux"))]
        pub(super) fn open(_pid: u32) -> Option<Watch> {
            None
        }

        pub(super) fn ended(&self) -> bool {
            let Some(fd) = self.0 else {
                return true;
            };
            let mut asked = libc::pollfd {
                fd,
                events: libc::POLLIN,
                revents: 0,
            };
            // SAFETY: one pollfd, for this call. A timeout of 0 doesn't block.
            unsafe { libc::poll(&mut asked, 1, 0) != 0 }
        }
    }

    impl Drop for Watch {
        fn drop(&mut self) {
            if let Some(fd) = self.0 {
                // SAFETY: opened above, and closed once.
                unsafe { libc::close(fd) };
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temporary(name: &str, holds: &[u8]) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!("mentis-held-{}-{name}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let file = dir.join(name);
        std::fs::write(&file, holds).unwrap();
        file
    }

    #[test]
    fn nothing_is_created_by_opening() {
        let missing = temporary("present", b"").with_file_name("absent");
        assert!(BrainFile::open(&missing).is_err());
        assert!(!missing.exists());
    }

    #[test]
    fn a_claim_is_exactly_its_bytes() {
        let boot = "0123456789abcdef0123456789abcdef";
        let whole = temporary("whole", boot.as_bytes());
        assert!(BrainFile::open(&whole).unwrap().says(boot).unwrap());
        let short = temporary("short", &boot.as_bytes()[..31]);
        assert!(!BrainFile::open(&short).unwrap().says(boot).unwrap());
        let long = temporary("long", format!("{boot}x").as_bytes());
        assert!(!BrainFile::open(&long).unwrap().says(boot).unwrap());
    }

    #[test]
    fn two_shared_holds_go_together() {
        let file = temporary("shared", b"");
        let (one, two) = (
            BrainFile::open(&file).unwrap(),
            BrainFile::open(&file).unwrap(),
        );
        assert_eq!(one.try_shared(), Tried::Taken);
        assert_eq!(two.try_shared(), Tried::Taken);
        one.unlock();
        two.unlock();
    }

    #[cfg(windows)]
    #[test]
    fn the_watch_says_when_a_real_child_ends_with_nothing_else_having_run() {
        let mut child = std::process::Command::new("cmd")
            .args(["/C", "ping -n 60 127.0.0.1 >NUL"])
            .spawn()
            .unwrap();
        let watch = ProcessWatch::open(child.id()).unwrap();
        assert!(!watch.ended());
        child.kill().unwrap();
        // The watch's own answer, with no wait of any other kind: a kill isn't synchronous.
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
        while !watch.ended() {
            assert!(std::time::Instant::now() < deadline);
            std::thread::yield_now();
        }
        child.wait().unwrap();
    }

    #[test]
    fn a_pid_nothing_can_open_gives_no_watch() {
        // Not a pid any system issues (Windows's are multiples of 4; Linux's stop at 2^22).
        assert!(ProcessWatch::open(0x7FFF_FFF1).is_none());
    }
}
