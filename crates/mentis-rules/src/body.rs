//! Reading a stored body as Python's `json.loads` and `dict.get` would, for the little the rules
//! need: a named field's truth and text, and the shape `_blank` keeps. Nothing else in a body is
//! decoded, so a Turn's words cost nothing here.

use std::fmt;

use serde::de::{self, Deserialize, DeserializeSeed, Deserializer, IgnoredAny, MapAccess, Visitor};

/// A field, as `body.get(name) or ...` reads it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Field {
    /// Absent, or false to Python: `null`, `""`, `0`, `false`, `[]`, `{}`.
    Nothing,
    Text(String),
    /// True to Python and not a string. What a route would show is Python's to say.
    NotText,
}

struct FieldVisitor;

fn truth(value: bool) -> Field {
    if value {
        Field::NotText
    } else {
        Field::Nothing
    }
}

impl<'de> Visitor<'de> for FieldVisitor {
    type Value = Field;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("a JSON value")
    }

    fn visit_unit<E>(self) -> Result<Field, E> {
        Ok(Field::Nothing)
    }

    fn visit_bool<E>(self, value: bool) -> Result<Field, E> {
        Ok(truth(value))
    }

    fn visit_i64<E>(self, value: i64) -> Result<Field, E> {
        Ok(truth(value != 0))
    }

    fn visit_u64<E>(self, value: u64) -> Result<Field, E> {
        Ok(truth(value != 0))
    }

    fn visit_f64<E>(self, value: f64) -> Result<Field, E> {
        Ok(truth(value != 0.0))
    }

    fn visit_str<E: de::Error>(self, value: &str) -> Result<Field, E> {
        Ok(if value.is_empty() {
            Field::Nothing
        } else {
            Field::Text(value.to_owned())
        })
    }

    fn visit_seq<A: de::SeqAccess<'de>>(self, mut seq: A) -> Result<Field, A::Error> {
        let any = seq.next_element::<IgnoredAny>()?.is_some();
        while seq.next_element::<IgnoredAny>()?.is_some() {}
        Ok(truth(any))
    }

    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Field, A::Error> {
        let any = map.next_entry::<IgnoredAny, IgnoredAny>()?.is_some();
        while map.next_entry::<IgnoredAny, IgnoredAny>()?.is_some() {}
        Ok(truth(any))
    }
}

impl<'de> Deserialize<'de> for Field {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Field, D::Error> {
        deserializer.deserialize_any(FieldVisitor)
    }
}

/// The fields of one body that were asked for.
struct Fields<'a>(&'a [&'a str]);

impl<'de> Visitor<'de> for Fields<'_> {
    type Value = Vec<Field>;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("a body")
    }

    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Vec<Field>, A::Error> {
        let mut found = vec![Field::Nothing; self.0.len()];
        while let Some(key) = map.next_key::<String>()? {
            match self.0.iter().position(|name| *name == key) {
                Some(at) => found[at] = map.next_value()?,
                None => {
                    map.next_value::<IgnoredAny>()?;
                }
            }
        }
        Ok(found)
    }
}

impl<'de> DeserializeSeed<'de> for Fields<'_> {
    type Value = Vec<Field>;

    fn deserialize<D: Deserializer<'de>>(self, deserializer: D) -> Result<Vec<Field>, D::Error> {
        deserializer.deserialize_any(self)
    }
}

/// `(body or {})`'s empty side: every value false to Python, whatever its type, as [`Field`] reads
/// truth. Asked only of what didn't read as an object, so an ordinary body isn't read twice.
fn is_false(body_json: &str) -> bool {
    matches!(serde_json::from_str(body_json), Ok(Field::Nothing))
}

/// These fields of a body as the record stores it, or `None` for a body that is true to Python and
/// not an object, which raises there, or can't be read here, such as one holding a lone surrogate
/// in a field asked for.
pub fn fields(body_json: &str, names: &[&str]) -> Option<Vec<Field>> {
    let mut reader = serde_json::Deserializer::from_str(body_json);
    let found = Fields(names).deserialize(&mut reader);
    match found.and_then(|found| reader.end().map(|()| found)) {
        Ok(found) => Some(found),
        Err(_) => is_false(body_json).then(|| vec![Field::Nothing; names.len()]),
    }
}

/// The shape `_blank` keeps of a value.
enum Shape {
    List,
    Object,
    Other,
}

struct ShapeVisitor;

impl<'de> Visitor<'de> for ShapeVisitor {
    type Value = Shape;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("a JSON value")
    }

    fn visit_unit<E>(self) -> Result<Shape, E> {
        Ok(Shape::Other)
    }

    fn visit_bool<E>(self, _: bool) -> Result<Shape, E> {
        Ok(Shape::Other)
    }

    fn visit_i64<E>(self, _: i64) -> Result<Shape, E> {
        Ok(Shape::Other)
    }

    fn visit_u64<E>(self, _: u64) -> Result<Shape, E> {
        Ok(Shape::Other)
    }

    fn visit_f64<E>(self, _: f64) -> Result<Shape, E> {
        Ok(Shape::Other)
    }

    fn visit_str<E>(self, _: &str) -> Result<Shape, E> {
        Ok(Shape::Other)
    }

    fn visit_seq<A: de::SeqAccess<'de>>(self, mut seq: A) -> Result<Shape, A::Error> {
        while seq.next_element::<IgnoredAny>()?.is_some() {}
        Ok(Shape::List)
    }

    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Shape, A::Error> {
        while map.next_entry::<IgnoredAny, IgnoredAny>()?.is_some() {}
        Ok(Shape::Object)
    }
}

impl<'de> Deserialize<'de> for Shape {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Shape, D::Error> {
        deserializer.deserialize_any(ShapeVisitor)
    }
}

struct Blank;

impl<'de> Visitor<'de> for Blank {
    type Value = String;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("a body")
    }

    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<String, A::Error> {
        let mut parts = Vec::new();
        while let Some(key) = map.next_key::<String>()? {
            let shown = serde_json::to_string(&key).map_err(de::Error::custom)?;
            let value = match map.next_value::<Shape>()? {
                Shape::List => "[]",
                Shape::Object => "{}",
                Shape::Other => "\"\"",
            };
            parts.push(format!("{shown}: {value}"));
        }
        Ok(format!("{{{}}}", parts.join(", ")))
    }
}

/// `_blank`, `conversation/versions.py:258`: each key kept in its order, a list empty, an object
/// empty, anything else `""`. A body false to Python is `{}`. `None` where `_blank` raises, for a
/// body true to Python and not an object, or where it can't be read here.
pub fn blank(body_json: &str) -> Option<String> {
    let mut reader = serde_json::Deserializer::from_str(body_json);
    let found = de::Deserializer::deserialize_any(&mut reader, Blank);
    match found.and_then(|found| reader.end().map(|()| found)) {
        Ok(found) => Some(found),
        Err(_) => is_false(body_json).then(|| "{}".to_owned()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_field_is_what_python_s_or_would_take() {
        let got = fields(
            r#"{"a": "words", "b": "", "c": 0, "d": [], "e": {}, "f": null, "g": false,
                "h": 3, "i": [1], "j": {"k": 1}, "l": true, "m": 0.0, "n": 1.5}"#,
            &[
                "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "l", "m", "n", "absent",
            ],
        )
        .unwrap();
        let no = Field::Nothing;
        let other = Field::NotText;
        assert_eq!(
            got,
            [
                Field::Text("words".into()),
                no.clone(),
                no.clone(),
                no.clone(),
                no.clone(),
                no.clone(),
                no.clone(),
                other.clone(),
                other.clone(),
                other.clone(),
                other.clone(),
                no.clone(),
                other,
                no,
            ]
        );
    }

    #[test]
    fn a_lone_surrogate_elsewhere_in_the_body_costs_nothing_and_in_a_name_is_not_read() {
        assert_eq!(
            fields(r#"{"words": "\ud800", "name": "n"}"#, &["name"]),
            Some(vec![Field::Text("n".into())])
        );
        assert_eq!(fields(r#"{"name": "\ud800"}"#, &["name"]), None);
    }

    #[test]
    fn what_is_not_an_object_is_empty_if_false_and_otherwise_not_read() {
        for empty in ["null", "[]", "false", "0", "0.0", "-0", "\"\""] {
            assert_eq!(
                fields(empty, &["name"]),
                Some(vec![Field::Nothing]),
                "{empty}"
            );
        }
        for not in [
            "[1]",
            "3",
            "true",
            "\"x\"",
            "not json",
            "{} trailing",
            "0 trailing",
        ] {
            assert_eq!(fields(not, &["name"]), None, "{not}");
        }
    }

    #[test]
    fn blank_keeps_the_keys_in_order_and_empties_the_values() {
        assert_eq!(
            blank(r#"{"z": "x", "a": [1], "m": {"k": 1}, "n": null, "q": 3}"#).unwrap(),
            r#"{"z": "", "a": [], "m": {}, "n": "", "q": ""}"#
        );
        for empty in ["{}", "null", "[]", "false", "0", "0.0", "-0", "\"\""] {
            assert_eq!(blank(empty).as_deref(), Some("{}"), "{empty}");
        }
        for not in ["[1]", "3", "true", "\"x\"", "not json", "0 trailing"] {
            assert_eq!(blank(not), None, "{not}");
        }
    }
}
