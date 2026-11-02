//! The Rust front. It owns the public port, answers what the route table gives it and forwards
//! everything else to Python. `docs/rust/README.md` says who builds what.

pub mod front;
pub mod handlers;
pub mod launch;
pub mod live;
pub mod route_table;
pub mod worker_reads;

/// The handlers this build has. A route table can name no others. One line each.
#[rustfmt::skip]
pub const HANDLERS: &[&str] = &[
    "pulse",
    "names",
    "topics",
    "worker",
    "static",
];
