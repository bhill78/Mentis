//! `GET /fluid/api/magnets/<id>/read?mode=summary|page&source=&cursor=&types=`: one Magnet's sources, in
//! `ReadClass::Background`, so it can't queue Fluid or an agent. Contract: `docs/magnets/M1-contract.md`.
//!
//! Only this reads the definition, and it never writes one. No definition is Python's to say, which
//! tells a client that has none to use its store (`magnets/<id>/read` is no route of Python's, so 404).
//! No class place at all is 503 Busy. A source out of its share says so itself, in a 200.

use std::path::PathBuf;
use std::sync::atomic::Ordering;
use std::time::{Duration, Instant};

use mentis_ops::magnet::{
    MagnetArgs, MagnetDefinition, MagnetMode, MagnetRead, NotADefinition, is_information_type,
    reads_objects,
};
use mentis_ops::pyjson::Py;
use mentis_ops::window::Prepared;
use mentis_ops::{Cursor, ReadClass, ReadRequest};
use mentis_record::READ_SCOPE_LIMIT;

use super::query::{Query, bad_request, from_error};
use super::{Ask, Context, Door, Reply, Route};

pub const ROUTE: Route = Route {
    name: "magnet-read",
    door: Door::FluidGet,
    answer,
};

/// The rest of a read, once its scope has gone: what extraction may take beyond the scope's limit.
const FINISH_WITHIN: Duration = Duration::from_secs(4);
/// `_checks.MAX_BYTES`: nothing Python keeps is larger.
const MOST_BYTES: u64 = 256 * 1024;

fn sent(status: u16, value: &Py) -> Reply {
    Reply::Answer {
        status,
        content_type: "application/json",
        body: value.dumps().into_bytes(),
    }
}

/// `presentation/magnets/<id>.json`. `<id>` is the op's own check of `mag-[A-Za-z0-9_-]{1,60}`, made by
/// `MagnetDefinition::parse` on what this read, and made here first so no other path is ever opened.
fn definition_path(context: &Context, id: &str) -> Option<PathBuf> {
    let well_formed = id.len() > 4
        && id.len() <= 64
        && id.starts_with("mag-")
        && id[4..]
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-'));
    well_formed.then(|| {
        context
            .window
            .root()
            .join("presentation")
            .join("magnets")
            .join(format!("{id}.json"))
    })
}

fn answer(context: &Context, ask: &Ask) -> Reply {
    let Some(query) = Query::parse(&ask.query) else {
        return Reply::NotOwned;
    };
    let id = ask
        .path
        .strip_prefix("/fluid/api/magnets/")
        .and_then(|rest| rest.strip_suffix("/read"));
    let Some(path) = id.and_then(|id| definition_path(context, id)) else {
        return Reply::NotOwned;
    };
    let id = id.expect("a path came of it");
    match std::fs::metadata(&path) {
        Ok(meta) if meta.is_file() && meta.len() <= MOST_BYTES => {}
        _ => return Reply::NotOwned,
    }
    let Ok(text) = std::fs::read_to_string(&path) else {
        return Reply::NotOwned;
    };
    let magnet = match MagnetDefinition::parse(id, &text) {
        Ok(magnet) => magnet,
        Err(NotADefinition::Malformed(_)) => return Reply::NotOwned,
        // Never read as if it were this schema, and never left to a store path that would.
        Err(NotADefinition::LaterSchema(why)) => {
            return sent(200, &MagnetDefinition::all_unavailable(id, &why));
        }
    };

    let mode = match query.first("mode").unwrap_or("summary") {
        "summary" => MagnetMode::Summary,
        "page" => {
            let types = match query.first("types") {
                None => None,
                Some(raw) => {
                    let words: Vec<String> = raw.split(',').map(str::to_owned).collect();
                    if let Some(odd) = words.iter().find(|w| !is_information_type(w)) {
                        return bad_request(&format!("types: {odd:?} is not an information type"));
                    }
                    Some(words)
                }
            };
            MagnetMode::Page {
                source: query.first("source").map(str::to_owned),
                types,
            }
        }
        other => return bad_request(&format!("mode is 'summary' or 'page', not {other:?}")),
    };
    let wants_objects = match &mode {
        MagnetMode::Summary => false,
        MagnetMode::Page { types, .. } => reads_objects(types.as_deref(), &magnet),
    };
    let bundle = if wants_objects {
        context.window.bundle().map_err(|error| error.to_string())
    } else {
        Err("no objects were asked for".to_owned())
    };
    let request = ReadRequest {
        args: MagnetArgs {
            magnet,
            mode,
            bundle,
            gone: ask.gone.clone(),
        },
        cursor: query.first("cursor").map(|c| Cursor(c.to_owned())),
        limit: None,
        deadline: Instant::now() + READ_SCOPE_LIMIT,
    };
    let op = MagnetRead {
        window: &context.window,
    };
    match mentis_ops::run(&op, &*context.record, ReadClass::Background, &request) {
        // A place in the class is the whole request's, and so is a bad cursor: 503 and 400. Anything
        // else a source says for itself.
        Err(error) => from_error(error),
        Ok(mut read) => {
            let Prepared(plan) = read.rows.pop().expect("magnet_read answers one plan");
            let until = Instant::now() + FINISH_WITHIN;
            let gone = &ask.gone;
            let stop = || Instant::now() >= until || gone.load(Ordering::Relaxed);
            sent(200, &plan.finish(&context.window, &stop))
        }
    }
}

#[cfg(test)]
mod tests {
    use std::path::Path;
    use std::sync::Arc;

    use mentis_ops::window::Window;
    use mentis_record::{ReadClass, ReadScope, RecordError, RecordReader};

    use super::*;

    /// Every class at its cap.
    struct Full;

    impl RecordReader for Full {
        fn read_scope(&self, _class: ReadClass) -> Result<Box<dyn ReadScope>, RecordError> {
            Err(RecordError::Busy {
                class: "background",
            })
        }

        fn corpus_id(&self) -> &str {
            ""
        }
    }

    fn brain(name: &str, id: &str, definition: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!("magnet-route-{name}-{}", std::process::id()));
        let folder = root.join("presentation").join("magnets");
        std::fs::create_dir_all(&folder).unwrap();
        std::fs::write(folder.join(format!("{id}.json")), definition).unwrap();
        root
    }

    fn asking(root: &Path, id: &str, query: &str) -> Reply {
        let context = Context {
            dist: root.join("no-dist"),
            record: Arc::new(Full),
            snapshots: Arc::new(crate::front::snapshot::Snapshots::new(
                "127.0.0.1:9".parse().unwrap(),
                "s".into(),
            )),
            window: Arc::new(Window::new(root, &root.join("no-dist"))),
        };
        answer(
            &context,
            &Ask {
                gone: Arc::default(),
                method: "GET".into(),
                path: format!("/fluid/api/magnets/{id}/read"),
                query: query.into(),
                headers: Vec::new(),
            },
        )
    }

    const GOOD: &str = r#"{"id":"mag-a","schema_version":1,"selection":{},
        "sources":[{"kind":"conversation","conversation":"ent-1"}]}"#;

    fn says(reply: Reply) -> (u16, String) {
        match reply {
            Reply::Answer { status, body, .. } => (status, String::from_utf8(body).unwrap()),
            Reply::NotOwned => panic!("not owned"),
        }
    }

    #[test]
    fn no_definition_is_python_s_to_say_and_never_another_path() {
        let root = brain("none", "mag-a", GOOD);
        assert_eq!(asking(&root, "mag-b", ""), Reply::NotOwned);
        for odd in ["..%2Fx", "mag-a%2F..", "x", "mag-", "mag-a.from-ent-1"] {
            assert_eq!(asking(&root, odd, ""), Reply::NotOwned, "{odd}");
        }
        let broken = brain("broken", "mag-a", "{nope");
        assert_eq!(asking(&broken, "mag-a", ""), Reply::NotOwned);
    }

    #[test]
    fn a_full_class_is_503_for_the_whole_request() {
        let root = brain("busy", "mag-a", GOOD);
        let (status, body) = says(asking(&root, "mag-a", "mode=summary"));
        assert_eq!(status, 503);
        assert!(body.contains("Busy"), "{body}");
    }

    #[test]
    fn a_bad_request_says_so_before_any_read() {
        let root = brain("bad", "mag-a", GOOD);
        assert_eq!(says(asking(&root, "mag-a", "mode=everything")).0, 400);
        assert_eq!(says(asking(&root, "mag-a", "mode=page&types=video")).0, 400);
    }

    #[test]
    fn a_definition_from_a_later_schema_is_unavailable_and_said() {
        let later = GOOD.replace("\"schema_version\":1", "\"schema_version\":9");
        let root = brain("later", "mag-a", &later);
        let (status, body) = says(asking(&root, "mag-a", ""));
        assert_eq!(status, 200);
        assert!(body.contains("schema_version 9"), "{body}");
        assert!(body.contains("\"unavailable\""), "{body}");
    }
}
