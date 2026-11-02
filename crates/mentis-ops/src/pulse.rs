//! `GET /api/pulse`'s durable half, and where the record moved: `web/__init__.py:2564-2600`.
//!
//! The live half is the route's, from the snapshot (`contracts/live-snapshot.md`). This never reads
//! it, so a stalled Python can't hold up an answer.

use mentis_record::{Position, ReadScope};
use serde::Serialize;

use crate::moved::{self, Moved};
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest};

/// A pulse.
#[derive(Clone, Copy, Debug, Default)]
pub struct Pulse;

/// What a pulse asks.
#[derive(Clone, Debug, Default)]
pub struct PulseArgs {
    /// `?since=`, with nothing blank in it.
    pub since: Option<String>,
}

/// One pulse's answer. Its one row.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct PulseRow {
    #[serde(serialize_with = "crate::position_as_text")]
    pub durable: Position,
    /// Absent where `since` was not asked or is where the record is. `Some(None)` says
    /// "everything", which Python writes as `"moved": null`.
    pub moved: Option<Option<Moved>>,
}

impl ReadOp for Pulse {
    type Args = PulseArgs;
    type Row = PulseRow;

    const NAME: &'static str = "pulse";
    /// The position, and [`moved::STATEMENTS`] when `since` is behind it.
    const BUDGET: Budget = Budget {
        statements: 1 + moved::STATEMENTS,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<PulseArgs>,
    ) -> Result<ReadAnswer<PulseRow>, OpError> {
        let durable = scope.position();
        let since = request
            .args
            .since
            .as_deref()
            .filter(|since| !since.is_empty() && *since != durable.to_string());
        let moved = since
            .map(|since| moved::moved(scope, durable, since))
            .transpose()?;
        Ok(ReadAnswer {
            rows: vec![PulseRow { durable, moved }],
            as_of: durable,
            more: None,
            not_searched: Vec::new(),
        })
    }
}
