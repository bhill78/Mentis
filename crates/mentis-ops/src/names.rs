//! `GET /fluid/api/names`'s read: `_names`, `fluid/read.py:194`, over [`mentis_rules::name_reads`].

use mentis_record::{Id, ReadScope};
use mentis_rules::NameRead;
use serde::Serialize;

use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest};

/// Names.
#[derive(Clone, Copy, Debug, Default)]
pub struct Names;

/// The ids, as the route has already checked them.
#[derive(Clone, Debug, Default)]
pub struct NamesArgs {
    pub ids: Vec<Id>,
}

/// A held id, and its name if it has one. The route shows each as it does today.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct NameRow {
    pub id: String,
    pub name: Option<String>,
}

impl ReadOp for Names {
    type Args = NamesArgs;
    type Row = NameRow;

    const NAME: &'static str = "names";
    /// The position, and one [`mentis_rules::name_reads`].
    const BUDGET: Budget = Budget {
        statements: 1 + mentis_rules::STATEMENTS,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<NamesArgs>,
    ) -> Result<ReadAnswer<NameRow>, OpError> {
        let as_of = scope.position();
        let reads = mentis_rules::name_reads(scope, &request.args.ids)?;
        let mut rows = Vec::with_capacity(reads.len());
        for id in &request.args.ids {
            match reads.get(id) {
                None => {}
                Some(NameRead::NotPlain) => {
                    return Err(OpError::NotOwned {
                        why: format!("what {id} shows as is Python's to say"),
                    });
                }
                Some(NameRead::Unnamed) => rows.push(NameRow {
                    id: id.0.clone(),
                    name: None,
                }),
                Some(NameRead::Named(name)) => rows.push(NameRow {
                    id: id.0.clone(),
                    name: Some(name.clone()),
                }),
            }
        }
        Ok(ReadAnswer {
            rows,
            as_of,
            more: None,
            not_searched: Vec::new(),
        })
    }
}
