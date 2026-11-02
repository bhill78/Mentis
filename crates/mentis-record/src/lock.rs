//! `.mentis.lock`, shared, by the same OS lock and byte range as `spine/brainlock.py:77-81`:
//! `LockFileEx` on one byte at offset 0, and `flock` on POSIX. It dies with the process.

use std::fs::{File, OpenOptions};
use std::io;
use std::path::Path;

use crate::OPEN_LOCK;

/// Why the lock wasn't taken.
pub(crate) enum NotTaken {
    /// Somebody holds it exclusive: migrate, reconcile or restore.
    Exclusive,
    Failed(io::Error),
}

/// One shared hold, released when dropped.
pub(crate) struct OpenLock {
    file: File,
}

impl OpenLock {
    /// Creates the empty lock file if it is missing, as `brainlock._take` does (`a+b`).
    pub(crate) fn shared(root: &Path) -> Result<OpenLock, NotTaken> {
        let file = OpenOptions::new()
            .read(true)
            .append(true)
            .create(true)
            .open(root.join(OPEN_LOCK))
            .map_err(NotTaken::Failed)?;
        os::lock_shared(&file)?;
        Ok(OpenLock { file })
    }
}

impl Drop for OpenLock {
    fn drop(&mut self) {
        os::unlock(&self.file);
    }
}

#[cfg(windows)]
mod os {
    use std::fs::File;
    use std::io;
    use std::os::windows::io::AsRawHandle;

    use windows_sys::Win32::Foundation::{ERROR_IO_PENDING, ERROR_LOCK_VIOLATION, HANDLE};
    use windows_sys::Win32::Storage::FileSystem::{
        LOCKFILE_FAIL_IMMEDIATELY, LockFileEx, UnlockFileEx,
    };
    use windows_sys::Win32::System::IO::OVERLAPPED;

    use super::NotTaken;

    pub(super) fn lock_shared(file: &File) -> Result<(), NotTaken> {
        let handle = file.as_raw_handle() as HANDLE;
        // SAFETY: the handle is open for as long as `file` is, and the OVERLAPPED is zeroed (offset
        // 0, no event) and outlives this call, which with FAIL_IMMEDIATELY does not pend.
        let taken = unsafe {
            let mut at: OVERLAPPED = std::mem::zeroed();
            LockFileEx(handle, LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &mut at)
        };
        if taken != 0 {
            return Ok(());
        }
        let failed = io::Error::last_os_error();
        match failed.raw_os_error().map(|code| code as u32) {
            Some(ERROR_LOCK_VIOLATION | ERROR_IO_PENDING) => Err(NotTaken::Exclusive),
            _ => Err(NotTaken::Failed(failed)),
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
}

#[cfg(unix)]
mod os {
    use std::fs::File;
    use std::io;
    use std::os::fd::AsRawFd;

    use super::NotTaken;

    pub(super) fn lock_shared(file: &File) -> Result<(), NotTaken> {
        // SAFETY: the descriptor is open for as long as `file` is.
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_SH | libc::LOCK_NB) } == 0 {
            return Ok(());
        }
        let failed = io::Error::last_os_error();
        match failed.raw_os_error() {
            Some(libc::EWOULDBLOCK | libc::EACCES) => Err(NotTaken::Exclusive),
            _ => Err(NotTaken::Failed(failed)),
        }
    }

    pub(super) fn unlock(file: &File) {
        // SAFETY: as above. A failure leaves the close that follows to release it.
        unsafe {
            libc::flock(file.as_raw_fd(), libc::LOCK_UN);
        }
    }
}
