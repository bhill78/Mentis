//! The Rust front. It owns the public port, answers what the route table gives it and forwards
//! everything else to Python. `docs/rust/README.md` says who builds what.

pub mod front;
pub mod handlers;
pub mod launch;
pub mod live;
pub mod object_worker_reads;
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
    "posts",
    "conversation-collection",
    "thread-collection",
    "objects",
    "object",
    "references",
    "post-search",
    "object-refs",
    "document",
    "magnet-read",
    "magnet-activate",
    "stream-collection",
    "selection-collection",
    "fluid-participants",
    "latest",
    "fluid-conversations",
    "api-conversations",
    "api-participants",
    "home-needs-you",
    "needs-you-items",
    "needs-you",
    "post-anchors",
    "anchors",
    "changes",
    "response-set-history",
    "response-set-accounting",
    "personas",
    "conversation-fields",
    "turn-view",
    "intake",
    "turns",
    "thread-view",
    "decisions",
];
