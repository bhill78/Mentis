//! Operational acts, as `_act_of` (`spine/store.py:1697`) gives them to every reader.

use mentis_record::{RecordError, Row, Value};

use crate::OpError;
use crate::stored::{Object, Stored, python_says};

/// The columns every statement here reads an act by, in [`Act::read`]'s order.
#[macro_export]
#[doc(hidden)]
macro_rules! act_columns {
    () => {
        "id, act, at, actor, conversation, turn, execution, runtime, because, caused_by, about, detail"
    };
}

/// How many columns [`Act::read`] takes.
pub const COLUMNS: usize = 12;

/// One act. `about` and `detail` are `None` where their stored text isn't JSON, which `json.loads`
/// raises on: [`Act::about`] and [`Act::detail`] say so at the first reader that needs them.
#[derive(Clone, Debug)]
pub struct Act {
    pub id: String,
    pub act: Option<String>,
    pub at: f64,
    pub actor: Option<String>,
    pub conversation: Option<String>,
    pub turn: Option<String>,
    pub execution: Option<String>,
    pub runtime: Option<String>,
    pub because: Option<String>,
    pub caused_by: Option<String>,
    about_stored: Option<Stored>,
    detail_stored: Option<Stored>,
}

/// A text column, as a `str` or `None`.
pub fn text(row: &dyn Row, column: usize) -> Result<Option<String>, RecordError> {
    match row.value(column)? {
        Value::Null => Ok(None),
        Value::Text(bytes) => std::str::from_utf8(bytes)
            .map(|text| Some(text.to_owned()))
            .map_err(|_| RecordError::Sqlite {
                detail: format!("column {column} is not UTF-8"),
            }),
        _ => Err(RecordError::Sqlite {
            detail: format!("column {column} is not text"),
        }),
    }
}

/// A time column. What isn't a float would show differently from Python's, which keeps its type.
pub fn real(row: &dyn Row, column: usize) -> Result<f64, RecordError> {
    match row.value(column)? {
        Value::Real(at) => Ok(at),
        _ => Err(RecordError::Sqlite {
            detail: format!("column {column} is not a time"),
        }),
    }
}

impl Act {
    /// From [`COLUMNS`] columns starting at `from`.
    pub fn read(row: &dyn Row, from: usize) -> Result<Act, RecordError> {
        let column = |n: usize| text(row, from + n);
        Ok(Act {
            id: column(0)?.unwrap_or_default(),
            act: column(1)?,
            at: real(row, from + 2)?,
            actor: column(3)?,
            conversation: column(4)?,
            turn: column(5)?,
            execution: column(6)?,
            runtime: column(7)?,
            because: column(8)?,
            caused_by: column(9)?,
            about_stored: column(10)?.and_then(|about| Stored::parse(&about)),
            detail_stored: column(11)?.and_then(|detail| Stored::parse(&detail)),
        })
    }

    pub fn is(&self, act: &str) -> bool {
        self.act.as_deref() == Some(act)
    }

    pub fn about(&self) -> Result<&Stored, OpError> {
        self.about_stored
            .as_ref()
            .ok_or_else(|| python_says("an act whose `about` isn't JSON"))
    }

    pub fn detail(&self) -> Result<&Stored, OpError> {
        self.detail_stored
            .as_ref()
            .ok_or_else(|| python_says("an act whose `detail` isn't JSON"))
    }

    /// `act.get("detail") or {}`.
    pub fn detail_object(&self) -> Result<Object, OpError> {
        Object::or_empty(self.detail()?.text())
    }

    /// `act["about"]` as a list.
    pub fn about_items(&self) -> Result<Vec<Stored>, OpError> {
        self.about()?
            .items()
            .ok_or_else(|| python_says("an act whose `about` isn't a list"))
    }
}
