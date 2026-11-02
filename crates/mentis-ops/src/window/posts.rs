//! `GET /fluid/api/posts?ids=`, and with `&thread=1`: `read.posts` and `objects.thread_summaries`.
//! `read.posts` stays in Python for `commands.py:700`.

use std::collections::HashMap;

use mentis_extract::Bundle;
use mentis_record::{Flow, Id, Param, ReadScope, Value};
use mentis_rules::{Reading, id_list};

use super::classify::{self, Act};
use super::objects::{self, Wanted};
use super::reads::{
    self, BATCH, LINKED_INTO, Link, REPLIES_TO, by_home, closures, homes_of, in_force,
    links_from, links_to, names_of, numbers_of, text,
};
use super::{Finished, Prepared, Window, python_says};
use crate::pyjson::{self, Py, dict};
use crate::{Budget, OpError, ReadAnswer, ReadOp, ReadRequest};

/// `expectations`' and `forms`' acts, in one read.
const ACTS: &str = "SELECT id, act, turn, actor, at, about, detail, caused_by FROM operational \
     WHERE turn IN (SELECT value FROM json_each(?1)) \
       AND act IN ('expectation-recorded', 'decision-form', 'decision-form-attached') \
     ORDER BY seq";

const ROWS: &str = "SELECT id, family, def_name, link_relation, attributed_to, recorded_at \
     FROM entry WHERE id IN (SELECT value FROM json_each(?1))";

/// `objects.THREAD_MAX`.
const THREAD_MAX: usize = reads::PAGE_MAX as usize;

/// The op. `thread` is `&thread=1`.
pub struct Posts<'w> {
    pub window: &'w Window,
}

pub struct PostsArgs {
    pub ids: Vec<String>,
    /// `Some` for `&thread=1`: the bundle as it is now, read before a scope is taken.
    pub thread: Option<Bundle>,
}

/// An `entry` row as `_is_post` and the answer read it, without its body.
struct Row {
    is_post: bool,
    attributed_to: Option<String>,
    recorded_at: Py,
}

/// `thread_summaries`, with everything read that it will need.
pub struct ThreadPlan {
    bundle: Bundle,
    /// `(post, its rows, whether to add it)`, in `posts`' order, for the ones that aren't errors.
    closures: HashMap<String, Vec<reads::Reply>>,
    members: HashMap<String, Vec<String>>,
    wanted: HashMap<String, Option<Wanted>>,
    prepared: objects::PreparedInputs,
}

pub struct PostsPlan {
    out: Vec<Py>,
    limit: usize,
    thread: Option<ThreadPlan>,
}

fn body_list(body: &Py, name: &str) -> Result<Py, OpError> {
    if !body.truthy() {
        return Ok(Py::List(Vec::new()));
    }
    if !body.is_dict() {
        return Err(python_says("a post's body that isn't an object"));
    }
    Ok(match body.get(name) {
        Some(found) if found.truthy() => found.clone(),
        _ => Py::List(Vec::new()),
    })
}

/// `read.version_of`.
fn version_of(id: &str, reading: &Reading) -> String {
    if let Some(deleted) = &reading.deleted {
        return deleted.record.0.clone();
    }
    reading
        .revision
        .as_ref()
        .map_or_else(|| id.to_owned(), |revision| revision.current.0.clone())
}

impl ReadOp for Posts<'_> {
    type Args = PostsArgs;
    type Row = Prepared<PostsPlan>;

    const NAME: &'static str = "posts";
    /// The position; the rows; how they now read; homes; inclusions, and which are in force; parents;
    /// replies; the replies' homes and the parents' homes; two numberings; the acts; the names; agent
    /// work; and for `&thread=1` the closures, the lines, what the runs returned and what stands
    /// behind their references.
    const BUDGET: Budget = Budget {
        statements: 1
            + 1
            + mentis_rules::STATEMENTS
            + 1
            + 1
            + 2
            + 1
            + 1
            + 2
            + 2
            + 1
            + mentis_rules::STATEMENTS
            + classify::STATEMENTS
            + 1
            + mentis_rules::STATEMENTS
            + 1
            + objects::DESCRIBE_STATEMENTS,
    };

    fn read(
        &self,
        scope: &mut dyn ReadScope,
        request: &ReadRequest<PostsArgs>,
    ) -> Result<ReadAnswer<Prepared<PostsPlan>>, OpError> {
        let as_of = scope.position();
        let ids = &request.args.ids;

        let mut rows: HashMap<String, Row> = HashMap::with_capacity(ids.len());
        let list = id_list(ids.iter().map(String::as_str));
        scope.query(ROWS, &[Param::Text(&list)], &mut |row| {
            rows.insert(
                text(row, 0)?.unwrap_or_default(),
                Row {
                    is_post: text(row, 1)?.as_deref() == Some("entry")
                        && text(row, 2)?.as_deref() == Some(reads::CONTRIBUTION)
                        && matches!(row.value(3)?, Value::Null),
                    attributed_to: text(row, 4)?,
                    recorded_at: reads::number(row, 5)?,
                },
            );
            Ok(Flow::Continue)
        })?;

        let pids: Vec<&str> = ids
            .iter()
            .map(String::as_str)
            .filter(|id| rows.get(*id).is_some_and(|row| row.is_post))
            .collect();
        let asked: Vec<Id> = pids.iter().map(|id| Id((*id).to_owned())).collect();
        let now = mentis_rules::now_reads(scope, &asked)?;
        let homes = homes_of(scope, &pids)?;
        let numbers = numbers_of(scope, &homes)?;

        let mut included: HashMap<String, Vec<Link>> = HashMap::new();
        let linked = links_from(scope, LINKED_INTO, &pids)?;
        for link in in_force(scope, linked)? {
            included.entry(link.from.clone()).or_default().push(link);
        }

        let parents = reads::first_to(&links_from(scope, REPLIES_TO, &pids)?);
        let replies = links_to(scope, REPLIES_TO, &pids)?;
        let reply_home = {
            let from: Vec<&str> = replies.iter().map(|link| link.from.as_str()).collect();
            homes_of(scope, &from)?
        };
        let parent_home = {
            let to: Vec<&str> = parents.values().map(String::as_str).collect();
            homes_of(scope, &to)?
        };
        let parent_number = numbers_of(scope, &parent_home)?;

        let mut acts: Vec<Act> = Vec::new();
        if !pids.is_empty() {
            acts = classify::acts(scope, ACTS, &id_list(pids.iter().copied()))?;
        }
        let mut expectations: HashMap<&str, Vec<Py>> = HashMap::new();
        let mut forms: HashMap<&str, Vec<&str>> = HashMap::new();
        // As Python's two reads, one after the other: a post's forms it was asked on come first.
        for act in &acts {
            let Some(turn) = act.turn.as_deref() else {
                continue;
            };
            match act.act.as_str() {
                "expectation-recorded" => expectations
                    .entry(turn)
                    .or_default()
                    .push(Py::str(act.id.as_str())),
                "decision-form" => forms.entry(turn).or_default().push(&act.id),
                _ => {}
            }
        }
        for act in &acts {
            if act.act == "decision-form-attached"
                && let (Some(turn), Some(by)) = (act.turn.as_deref(), act.caused_by.as_deref())
                && !by.is_empty()
            {
                forms.entry(turn).or_default().push(by);
            }
        }

        let mut named: Vec<&str> = homes.values().map(String::as_str).collect();
        named.extend(included.values().flatten().map(|link| link.to.as_str()));
        named.extend(
            pids.iter()
                .filter_map(|id| rows.get(*id)?.attributed_to.as_deref()),
        );
        named.extend(parent_home.values().map(String::as_str));
        let names = names_of(scope, &named)?;

        let work = if pids.is_empty() {
            HashMap::new()
        } else {
            classify::classify(scope, &pids)?
        };

        // `counted`: a reply once under its parent, however many links say so.
        let mut counted: HashMap<&str, Vec<(&str, Option<&str>)>> = HashMap::new();
        for link in &replies {
            let kids = counted.entry(link.to.as_str()).or_default();
            if !kids.iter().any(|(from, _)| *from == link.from) {
                kids.push((
                    link.from.as_str(),
                    reply_home.get(&link.from).map(String::as_str),
                ));
            }
        }

        let mut out = Vec::with_capacity(ids.len());
        let mut listed: Vec<(String, usize, bool)> = Vec::new();
        for i in ids {
            let e = rows.get(i);
            let Some(e) = e.filter(|e| e.is_post) else {
                let why = if e.is_some() {
                    "not a post"
                } else {
                    "the record holds no such entry"
                };
                out.push(dict([("id", Py::str(i.as_str())), ("error", Py::str(why))]));
                continue;
            };
            let Some(cur) = now.get(&Id(i.clone())) else {
                return Err(python_says("a post this read didn't hold"));
            };
            if cur.python_says {
                return Err(python_says("a deleted post this can't read"));
            }
            let body = pyjson::loads(&cur.body_json)
                .ok_or_else(|| python_says("a body this can't read"))?;
            let parts = body_list(&body, "parts")?;
            let addressed_to = body_list(&body, "addressed_to")?;
            let home = homes.get(i).map(String::as_str);
            let author = e.attributed_to.as_deref();
            let kids = counted.get(i.as_str()).map_or(&[][..], Vec::as_slice);
            let parent = parents.get(i).map(String::as_str);

            let mut memberships = Vec::new();
            if let Some(home) = home {
                memberships.push(dict([
                    ("conversation", Py::str(home)),
                    ("via", Py::str("home")),
                ]));
            }
            for link in included.get(i).map_or(&[][..], Vec::as_slice) {
                memberships.push(dict([
                    ("conversation", Py::str(link.to.as_str())),
                    ("via", Py::str("linked")),
                    ("name", Py::opt_str(names.get(&link.to).map(String::as_str))),
                    ("link", Py::str(link.id.as_str())),
                    ("by", Py::opt_str(link.attributed_to.as_deref())),
                    ("at", link.recorded_at.clone()),
                ]));
            }
            let mut decision_forms: Vec<Py> = Vec::new();
            for form in forms.get(i.as_str()).map_or(&[][..], Vec::as_slice) {
                if !decision_forms.iter().any(|seen| seen.as_str() == Some(*form)) {
                    decision_forms.push(Py::str(*form));
                }
            }
            let reply_to_home = parent.and_then(|p| parent_home.get(p)).map(String::as_str);
            let deleted = cur.deleted.as_ref().map_or(Py::None, |deleted| {
                dict([
                    ("record", Py::str(deleted.record.0.as_str())),
                    ("at", Py::Float(deleted.at)),
                    ("by", Py::opt_str(deleted.by.as_ref().map(|by| by.0.as_str()))),
                    ("because", Py::opt_str(deleted.because.as_deref())),
                ])
            });
            let (versions, edited_at) = cur.revision.as_ref().map_or_else(
                || (Py::int(1), Py::None),
                |revision| (Py::int(revision.versions), Py::Float(revision.edited_at)),
            );
            let count = kids.len();
            out.push(dict([
                ("id", Py::str(i.as_str())),
                ("version", Py::Str(version_of(i, cur))),
                ("versions", versions),
                ("author", Py::opt_str(author)),
                (
                    "author_name",
                    Py::opt_str(author.map(|a| names.get(a).map_or(a, String::as_str))),
                ),
                ("at", e.recorded_at.clone()),
                ("edited_at", edited_at),
                ("deleted", deleted),
                ("parts", parts),
                ("addressed_to", addressed_to),
                ("home", Py::opt_str(home)),
                ("home_name", Py::opt_str(home.and_then(|h| names.get(h)).map(String::as_str))),
                ("number", numbers.get(i).map_or(Py::None, Py::int)),
                ("reply_to", Py::opt_str(parent)),
                ("reply_to_home", Py::opt_str(reply_to_home)),
                (
                    "reply_to_home_name",
                    Py::opt_str(reply_to_home.and_then(|h| names.get(h)).map(String::as_str)),
                ),
                (
                    "reply_to_number",
                    parent
                        .and_then(|p| parent_number.get(p))
                        .map_or(Py::None, Py::int),
                ),
                ("memberships", Py::List(memberships)),
                (
                    "expectations",
                    Py::List(expectations.get(i.as_str()).cloned().unwrap_or_default()),
                ),
                ("decision_forms", Py::List(decision_forms)),
                (
                    "replies",
                    dict([
                        ("count", Py::int(count)),
                        ("by_home", by_home(kids.iter().map(|(_, home)| *home))),
                    ]),
                ),
                ("agent_work", work.get(i).cloned().unwrap_or(Py::None)),
            ]));
            listed.push((i.clone(), out.len() - 1, parent.is_none()));
        }

        let thread = match &request.args.thread {
            None => None,
            Some(bundle) => Some(plan_thread(self.window, scope, bundle, &listed, &counted)?),
        };
        Ok(ReadAnswer {
            rows: vec![Prepared(PostsPlan {
                out,
                limit: BATCH,
                thread,
            })],
            as_of,
            more: None,
            not_searched: Vec::new(),
        })
    }
}

fn plan_thread(
    window: &Window,
    scope: &mut dyn ReadScope,
    bundle: &Bundle,
    listed: &[(String, usize, bool)],
    counted: &HashMap<&str, Vec<(&str, Option<&str>)>>,
) -> Result<ThreadPlan, OpError> {
    let roots: Vec<&str> = listed
        .iter()
        .map(|(id, _, _)| id.as_str())
        .filter(|id| counted.get(id).is_some_and(|kids| !kids.is_empty()))
        .collect();
    let threads = closures(scope, &roots)?;
    let mut members: HashMap<String, Vec<String>> = HashMap::new();
    for (id, _, top) in listed {
        if *top && let Some(rows) = threads.get(id) {
            let from = rows.len().saturating_sub(THREAD_MAX);
            members.insert(
                id.clone(),
                rows[from..].iter().map(|row| row.id.clone()).collect(),
            );
        }
    }
    let mut named: Vec<&str> = Vec::new();
    for (id, _, _) in listed {
        if !named.contains(&id.as_str()) {
            named.push(id);
        }
    }
    let mut seen: std::collections::HashSet<&str> = named.iter().copied().collect();
    for rows in members.values() {
        for id in rows {
            if seen.insert(id.as_str()) {
                named.push(id);
            }
        }
    }
    let asked: Vec<Id> = named.iter().map(|id| Id((*id).to_owned())).collect();
    let lines = mentis_rules::lines_of(scope, &asked)?;
    let returned = objects::returned_of(scope, &named)?;

    let mut wanted: HashMap<String, Option<Wanted>> = HashMap::with_capacity(named.len());
    for id in &named {
        let line = lines.get(&Id((*id).to_owned()));
        let reading = line.filter(|line| line.deletion.is_none() && !line.versions.is_empty());
        wanted.insert(
            (*id).to_owned(),
            reading.map(|line| {
                Wanted::new(
                    id,
                    line.versions[line.versions.len() - 1].clone(),
                    returned.get(*id).cloned().unwrap_or_default(),
                    bundle,
                    window,
                )
            }),
        );
    }
    let all: Vec<&Wanted> = wanted.values().flatten().collect();
    let prepared = objects::prepare_kinds(window, scope, &all)?;
    Ok(ThreadPlan {
        bundle: bundle.clone(),
        closures: threads,
        members,
        wanted,
        prepared,
    })
}

impl PostsPlan {
    /// What's left: each post's `thread`, by `chip_kind`, and the whole answer. No scope is held.
    pub fn finish(mut self, window: &Window) -> Result<Finished, OpError> {
        if let Some(plan) = self.thread.take() {
            let mut memo: HashMap<String, Option<Vec<String>>> = HashMap::new();
            for p in &mut self.out {
                if p.get("error").is_some_and(Py::truthy) {
                    continue;
                }
                let Some(id) = p.get("id").and_then(Py::as_str).map(str::to_owned) else {
                    continue;
                };
                let none = Vec::new();
                let rows = plan.closures.get(&id).unwrap_or(&none);
                let mut counts: Vec<(String, u64)> = Vec::new();
                let mut extracted = true;
                let empty = Vec::new();
                let under = plan.members.get(&id).unwrap_or(&empty);
                for pid in std::iter::once(&id).chain(under.iter()) {
                    let got = match memo.get(pid) {
                        Some(known) => known.clone(),
                        None => {
                            let read = match plan.wanted.get(pid).and_then(Option::as_ref) {
                                None => Some(Vec::new()),
                                Some(wanted) => {
                                    objects::kinds_of(window, &plan.bundle, wanted, &plan.prepared)?
                                }
                            };
                            memo.insert(pid.clone(), read.clone());
                            read
                        }
                    };
                    let Some(got) = got else {
                        extracted = false;
                        continue;
                    };
                    for kind in got {
                        match counts.iter_mut().find(|(have, _)| *have == kind) {
                            Some(found) => found.1 += 1,
                            None => counts.push((kind, 1)),
                        }
                    }
                }
                p.set(
                    "thread",
                    dict([
                        ("replies", Py::int(rows.len())),
                        (
                            "by_home",
                            by_home(rows.iter().map(|row| row.home.as_deref())),
                        ),
                        (
                            "kinds",
                            Py::List(
                                counts
                                    .into_iter()
                                    .map(|(kind, n)| Py::List(vec![Py::Str(kind), Py::int(n)]))
                                    .collect(),
                            ),
                        ),
                        ("extracted", Py::Bool(extracted)),
                    ]),
                );
            }
        }
        Ok(Finished::Answer(dict([
            ("posts", Py::List(self.out)),
            ("limit", Py::int(self.limit)),
        ])))
    }
}
