//! `capabilities`: `Surface.capabilities`, `worker.py:2131`. Names only, from code and not from the
//! record, so nothing is read. `tests/agent_reads.rs` holds this list to `api.capability_names()`.
//! The sentence about `delegate` is the agent door's.

use mentis_record::ReadScope;
use serde::Serialize;

use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest};

/// `types.Capability`'s values, sorted.
const NAMES: [&str; 18] = [
    "build_ui",
    "call_mentis_tools",
    "deliver_at_start",
    "deliver_to_live",
    "discover",
    "drive_browser",
    "invoke_headless",
    "isolate_from_machine_config",
    "list_models",
    "observe_actual_effort",
    "observe_actual_model",
    "observe_capacity",
    "reach_local_models",
    "request_effort",
    "request_model",
    "resume",
    "session_identity",
    "write_unattended",
];

/// Capabilities.
#[derive(Clone, Copy, Debug, Default)]
pub struct Capabilities;

/// The names a `requires` may use.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct CapabilityNames {
    pub capabilities: Vec<String>,
    pub count: u64,
}

impl ReadOp for Capabilities {
    type Args = ();
    type Row = CapabilityNames;

    const NAME: &'static str = "capabilities";
    /// The position, which `run` takes the scope for and every op answers with.
    const BUDGET: Budget = Budget { statements: 1 };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        _request: &ReadRequest<()>,
    ) -> Result<ReadAnswer<CapabilityNames>, OpError> {
        Ok(ReadAnswer {
            rows: vec![CapabilityNames {
                capabilities: NAMES.iter().map(|name| (*name).to_owned()).collect(),
                count: NAMES.len() as u64,
            }],
            as_of: scope.position(),
            more: None,
            not_searched: Vec::new(),
        })
    }
}
