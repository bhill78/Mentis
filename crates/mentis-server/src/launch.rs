//! What the launcher, the front, Python and an installer agree on. Contract:
//! `docs/rust/contracts/launcher.md`. The launcher itself is P1.5's, as `src/bin/mentis-launch.rs`.

use std::time::Duration;

use serde::{Deserialize, Serialize};

/// The header carrying the caller's real address, from the front to Python on the private port.
pub const PEER_HEADER: &str = "X-Mentis-Peer";

/// The header proving a request came from this boot's front. The same value guards `/private/*`.
/// The front strips any inbound copy of it and of [`PEER_HEADER`] before anything else.
pub const SECRET_HEADER: &str = "X-Mentis-Boot-Secret";

/// How the launcher hands the secret to both processes. Never a command-line argument.
pub const SECRET_ENV: &str = "MENTIS_BOOT_SECRET";

/// Random bytes in a secret, before URL-safe base64. As `secrets.token_urlsafe(32)`.
pub const SECRET_BYTES: usize = 32;

/// Where the front ends a planned stop. Only ever loopback, with the secret; 404 otherwise.
pub const STOP_PATH: &str = "/private/stop";

/// `/private/*` belongs to this boot's machinery. The front answers it itself on the public port
/// and never forwards it, so the public port can't reach Python's private routes.
pub const PRIVATE_PREFIX: &str = "/private/";

/// A planned stop finishes what it has forwarded for up to this long: past the worker's own 30 s
/// (`ASK_TIMEOUT_S`, `worker.py:6656`), so the front never cuts a call the worker still waits on.
pub const DRAIN_LIMIT: Duration = Duration::from_secs(35);

/// A private port, when none is named: the public port plus this. So 8760 is 18760, and the
/// bench's 8831-8839, which its gate watches, keep their private ports outside that range.
pub const PRIVATE_PORT_OFFSET: u16 = 10000;

/// Exit status of a process that refused to start, in words on stderr. Python's, as `web.main`.
pub const EXIT_REFUSED: i32 = 3;

/// The launcher's state file: `<run dir>/launch.json`, readable by this user alone, written
/// atomically once both answer. Not in the Brain.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct LaunchState {
    /// `format` of this file. Any other is refused by whoever reads it.
    pub format: u32,
    /// The Brain directory.
    pub brain: String,
    pub public_host: String,
    pub public_port: u16,
    /// Always loopback.
    pub private_port: u16,
    /// Told to Python as `--answers-at`, and so to agents.
    pub answers_at: String,
    pub secret: String,
    pub front: Started,
    pub python: Started,
}

pub const STATE_FORMAT: u32 = 1;

/// One process the launcher started.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Started {
    pub pid: u32,
    /// As given, for telling a reused pid apart with the process's start time.
    pub executable: String,
    /// Where its stdout and stderr are appended.
    pub log: String,
}

/// The default private port for a public one. `None` where it would not fit: name one.
pub fn default_private_port(public: u16) -> Option<u16> {
    public.checked_add(PRIVATE_PORT_OFFSET)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn private_ports_sit_outside_the_ranges_already_in_use() {
        assert_eq!(default_private_port(8760), Some(18760));
        assert_eq!(default_private_port(8831), Some(18831));
        assert_eq!(default_private_port(60000), None);
    }

    #[test]
    fn the_state_file_round_trips() {
        let state = LaunchState {
            format: STATE_FORMAT,
            brain: r"C:\b".into(),
            public_host: "127.0.0.1".into(),
            public_port: 8760,
            private_port: 18760,
            answers_at: "http://127.0.0.1:8760".into(),
            secret: "s".into(),
            front: Started {
                pid: 1,
                executable: "mentis-server.exe".into(),
                log: "f.log".into(),
            },
            python: Started {
                pid: 2,
                executable: "python.exe".into(),
                log: "p.log".into(),
            },
        };
        let text = serde_json::to_string(&state).unwrap();
        assert_eq!(serde_json::from_str::<LaunchState>(&text).unwrap(), state);
    }
}
