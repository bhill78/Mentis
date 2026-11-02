//! What the front answers itself. Each route is one file here, one line of [`ROUTES`], and one
//! line of [`crate::HANDLERS`], and a route table names it by that name.

use std::path::PathBuf;
use std::sync::Arc;

use mentis_record::RecordReader;

use crate::front::snapshot::Snapshots;

mod names;
mod pulse;
mod query;
mod static_files;
mod topics;
mod worker;

/// Everything this build can answer.
#[rustfmt::skip]
pub const ROUTES: &[Route] = &[
    pulse::ROUTE,
    names::ROUTE,
    topics::ROUTE,
    worker::ROUTE,
    static_files::ROUTE,
];

/// The checks a route's door runs before its handler, in Python's order: Host, client header,
/// grant. So a handler is only ever reached by a request the door it replaced would have let by.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Door {
    /// `do_GET`'s last line: Host only.
    Static,
    /// `_api` (`web/__init__.py:6876`): Host, client header, then a grant is refused.
    Api,
    /// Fluid's GET (`fluid/__init__.py:351`): Host, client header, then a grant is refused.
    FluidGet,
    /// `POST /api/worker`, which has a door of its own: `front/door.rs`.
    Worker,
}

impl Door {
    /// What this door says to a grant. `None` if it doesn't look at one.
    pub const fn grant_wording(self) -> Option<&'static str> {
        match self {
            Door::Static | Door::Worker => None,
            Door::Api => {
                Some("a worker grant authorises the four reads at /api/worker and nothing else")
            }
            Door::FluidGet => Some("a worker grant authorises /api/worker and nothing else"),
        }
    }

    pub const fn checks_client(self) -> bool {
        !matches!(self, Door::Static | Door::Worker)
    }
}

/// A route this build owns.
#[derive(Clone, Copy, Debug)]
pub struct Route {
    /// Its name in the table and in [`crate::HANDLERS`].
    pub name: &'static str,
    pub door: Door,
    /// Runs on a blocking thread, so a handler may read the Brain or a file.
    pub answer: fn(&Context, &Ask) -> Reply,
}

/// What a handler has to work with, for the front's whole life.
pub struct Context {
    /// `--dist`.
    pub dist: PathBuf,
    /// The Brain, read only, holding `.mentis.lock` shared.
    pub record: Arc<dyn RecordReader>,
    /// What the front knows of run state, for the pulse's live half.
    pub snapshots: Arc<Snapshots>,
}

/// One request, as a handler sees it. Text is Latin-1 decoded, as Python's is.
#[derive(Clone, Debug)]
pub struct Ask {
    pub method: String,
    /// As sent, before `?`.
    pub path: String,
    /// As sent, after `?`. Empty without one.
    pub query: String,
    pub headers: Vec<(String, String)>,
}

/// What a handler decided.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Reply {
    /// As `_send` would send it.
    Answer {
        status: u16,
        content_type: &'static str,
        body: Vec<u8>,
    },
    /// A case of this route Rust doesn't own. The request goes on to Python, unchanged, and the
    /// handler has answered nothing.
    NotOwned,
}

/// The route with this name, if this build has it.
pub fn find(name: &str) -> Option<&'static Route> {
    ROUTES.iter().find(|route| route.name == name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_list_a_table_is_checked_against_is_the_list_that_can_answer() {
        let answerable: Vec<&str> = ROUTES.iter().map(|route| route.name).collect();
        assert_eq!(answerable, crate::HANDLERS);
    }
}
