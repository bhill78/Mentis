//! `POST /api/worker`. Its door reads a body and answers through the tail, which is the connection's
//! to do, so this is only the name a route table gives it: `front/door.rs` has the rest.

use super::{Ask, Context, Door, Reply, Route};

pub const ROUTE: Route = Route {
    name: "worker",
    door: Door::Worker,
    answer,
};

fn answer(_context: &Context, _ask: &Ask) -> Reply {
    Reply::NotOwned
}
