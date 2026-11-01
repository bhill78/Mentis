//! The Rust front. It owns the public port, answers what the route table gives it and forwards
//! everything else to Python. Interfaces only so far: `docs/rust/README.md` says who builds what.

pub mod launch;
pub mod live;
pub mod route_table;

/// The handlers this build has. A route table can name no others. Empty: no route behaviour yet.
pub const HANDLERS: &[&str] = &[];
