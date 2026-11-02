//! Fluid's files: `_static` (`web/__init__.py:6471-6489`), P1.2's by plan section 2. The table
//! entry that turns it on is P1.3's.
//!
//! **It answers only paths and types it can't get wrong,** and anything else is `NotOwned`, so
//! Python decides. A `%`, a `;`, a `..` or a backslash is Python's to decode and resolve: its
//! answer is the contract, and an answer of Python's can't differ from itself.

use std::path::Path;

use super::{Ask, Context, Door, Reply, Route};
use crate::front::answers::json_object;

pub const ROUTE: Route = Route {
    name: "static",
    door: Door::Static,
    answer,
};

/// `render_check`'s own script, which the page must not be handed (`:6485`).
const NOT_SERVED: &str = "render-check.js";
const INDEX: &str = "index.html";

/// `mimetypes.guess_type`, for what a Fluid build holds, read on this machine against Python
/// 3.12.10. Python's table also takes from the Windows registry, so an extension not listed here
/// is left to Python rather than guessed.
fn content_type(extension: &str) -> Option<&'static str> {
    Some(match extension {
        "html" => "text/html",
        "js" => "text/javascript",
        "css" => "text/css",
        "jpg" => "image/jpeg",
        "json" => "application/json",
        _ => return None,
    })
}

/// Segments of letters, digits, `.`, `_` and `-`, none of them `.`, `..`, ending in a dot, or a
/// name Windows keeps for a device. `/` is the index.
fn plain_path(path: &str) -> bool {
    if path == "/" {
        return true;
    }
    let Some(rest) = path.strip_prefix('/') else {
        return false;
    };
    rest.split('/').all(|segment| {
        !segment.is_empty()
            && !segment.ends_with('.')
            && segment
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'))
            && !is_device_name(segment)
    })
}

fn is_device_name(segment: &str) -> bool {
    let stem = segment.split('.').next().unwrap_or("").to_ascii_uppercase();
    matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        || ((stem.starts_with("COM") || stem.starts_with("LPT"))
            && stem.len() == 4
            && stem.as_bytes()[3].is_ascii_digit())
}

fn answer(context: &Context, ask: &Ask) -> Reply {
    // A table has to name `/api/*` and `/fluid/api/*` above this rule (`contracts/route-table.md`).
    // If one doesn't, Python's API still answers.
    if ask.path.starts_with("/api/") || ask.path.starts_with("/fluid/api/") {
        return Reply::NotOwned;
    }
    answer_from(&context.dist, &ask.path)
}

fn answer_from(dist: &Path, path: &str) -> Reply {
    if !plain_path(path) {
        return Reply::NotOwned;
    }
    let root = match dist.canonicalize() {
        Ok(root) if root.join(INDEX).is_file() => root,
        Ok(_) | Err(_) => {
            return Reply::Answer {
                status: 404,
                content_type: "application/json",
                body: json_object(&[
                    (
                        "error",
                        "this Mentis serves its API only (/api/...): Fluid is not built (apps/fluid-web: npm run build)",
                    ),
                    ("kind", "NotFound"),
                ])
                .into_bytes(),
            };
        }
    };
    let target = root.join(path.trim_start_matches('/')).canonicalize();
    let file = match target {
        Ok(target)
            if target.is_file()
                && target.starts_with(&root)
                && target != root
                && target.file_name().is_some_and(|name| name != NOT_SERVED) =>
        {
            target
        }
        // One page: an address that isn't a built file is Fluid's own.
        _ => root.join(INDEX),
    };
    let Some(content_type) = file
        .extension()
        .and_then(|extension| extension.to_str())
        .and_then(content_type)
    else {
        return Reply::NotOwned;
    };
    match std::fs::read(&file) {
        Ok(body) => Reply::Answer {
            status: 200,
            content_type,
            body,
        },
        // Mid-build, or a permission: Python's own answer is the one to give.
        Err(_) => Reply::NotOwned,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dist(name: &str) -> std::path::PathBuf {
        let root =
            std::env::temp_dir().join(format!("mentis-static-{}-{name}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("assets")).unwrap();
        std::fs::write(root.join("index.html"), "<index>").unwrap();
        std::fs::write(root.join("render-check.js"), "secret").unwrap();
        std::fs::write(root.join("assets/app-1.js"), "js").unwrap();
        std::fs::write(root.join("assets/app-1.css"), "css").unwrap();
        std::fs::write(root.join("notes.md"), "words").unwrap();
        root
    }

    struct NoRecord;

    impl mentis_record::RecordReader for NoRecord {
        fn read_scope(
            &self,
            _class: mentis_record::ReadClass,
        ) -> Result<Box<dyn mentis_record::ReadScope>, mentis_record::RecordError> {
            Err(mentis_record::RecordError::Sqlite {
                detail: "not in these tests".into(),
            })
        }

        fn corpus_id(&self) -> &str {
            ""
        }
    }

    fn served(status: u16, content_type: &'static str, body: &[u8]) -> Reply {
        Reply::Answer {
            status,
            content_type,
            body: body.to_vec(),
        }
    }

    #[test]
    fn the_index_and_built_files_are_served_with_python_s_types() {
        let root = dist("built");
        assert_eq!(
            answer_from(&root, "/"),
            served(200, "text/html", b"<index>")
        );
        assert_eq!(
            answer_from(&root, "/assets/app-1.js"),
            served(200, "text/javascript", b"js")
        );
        assert_eq!(
            answer_from(&root, "/assets/app-1.css"),
            served(200, "text/css", b"css")
        );
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn an_address_that_is_no_built_file_is_the_page() {
        let root = dist("page");
        for path in ["/fluid", "/assets/nope.js", "/assets", "/render-check.js"] {
            assert_eq!(
                answer_from(&root, path),
                served(200, "text/html", b"<index>"),
                "{path}"
            );
        }
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn anything_python_would_have_to_interpret_is_python_s() {
        let root = dist("odd");
        for path in [
            "//index.html",
            "/../index.html",
            "/assets/../index.html",
            "/%2e%2e/index.html",
            "/index.html;x",
            "/a\\b",
            "/a#b",
            "/assets//app-1.js",
            "/assets/",
            "/index.html.",
            "/CON",
            "/nul.txt",
            "/com1",
            "http://x/index.html",
            "/caf\u{e9}",
            "/notes.md",
        ] {
            assert_eq!(answer_from(&root, path), Reply::NotOwned, "{path}");
        }
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn with_nothing_built_it_says_so_as_python_does() {
        let root = dist("unbuilt").join("not-here");
        assert_eq!(
            answer_from(&root, "/"),
            served(
                404,
                "application/json",
                br#"{"error": "this Mentis serves its API only (/api/...): Fluid is not built (apps/fluid-web: npm run build)", "kind": "NotFound"}"#
            )
        );
    }

    #[test]
    fn the_api_is_never_a_file_even_if_a_table_forgets() {
        let context = Context {
            dist: dist("api"),
            record: std::sync::Arc::new(NoRecord),
        };
        let ask = |path: &str| Ask {
            method: "GET".into(),
            path: path.into(),
            query: String::new(),
            headers: Vec::new(),
        };
        assert_eq!(answer(&context, &ask("/api/x")), Reply::NotOwned);
        assert_eq!(answer(&context, &ask("/fluid/api/x")), Reply::NotOwned);
        assert_eq!(
            answer(&context, &ask("/apiary")),
            served(200, "text/html", b"<index>")
        );
        std::fs::remove_dir_all(&context.dist).unwrap();
    }
}
