//! A JSON value as the record stores it, handed on untouched. Bodies and details are the record's
//! own: decoding one to carry it would sort its keys and move its floats, and an answer has to say
//! what Python's says.

use mentis_rules::body::Field;
use serde::de::{self, Deserializer, MapAccess, Visitor};
use serde::ser::SerializeMap;
use serde::{Deserialize, Serialize, Serializer};
use serde_json::value::RawValue;
use std::fmt;

use crate::OpError;

/// One JSON value, as stored.
#[derive(Clone, Debug)]
pub struct Stored(Box<RawValue>);

impl PartialEq for Stored {
    fn eq(&self, other: &Stored) -> bool {
        self.0.get() == other.0.get()
    }
}

impl Eq for Stored {}

impl Serialize for Stored {
    fn serialize<S: Serializer>(&self, to: S) -> Result<S::Ok, S::Error> {
        self.0.serialize(to)
    }
}

impl<'de> Deserialize<'de> for Stored {
    fn deserialize<D: Deserializer<'de>>(from: D) -> Result<Stored, D::Error> {
        Box::<RawValue>::deserialize(from).map(Stored)
    }
}

impl Stored {
    /// `None` for text that isn't one JSON value, which `json.loads` would raise on or would read
    /// as `NaN`.
    pub fn parse(text: &str) -> Option<Stored> {
        serde_json::from_str(text).ok()
    }

    pub fn null() -> Stored {
        Stored(RawValue::from_string("null".to_owned()).expect("null is JSON"))
    }

    /// A value made here, as JSON.
    pub fn of<T: Serialize>(value: &T) -> Stored {
        let text = serde_json::to_string(value).expect("what is made here is always JSON");
        Stored(RawValue::from_string(text).expect("to_string makes JSON"))
    }

    pub fn text(&self) -> &str {
        self.0.get()
    }

    pub fn is_null(&self) -> bool {
        self.text() == "null"
    }

    /// `value is True`.
    pub fn is_true(&self) -> bool {
        self.text() == "true"
    }

    /// As `value or ...` reads it. `None` for a string this can't read, such as a lone surrogate.
    pub fn field(&self) -> Option<Field> {
        serde_json::from_str(self.text()).ok()
    }

    /// True to Python. `None` where that can't be read here.
    pub fn truthy(&self) -> Option<bool> {
        Some(!matches!(self.field()?, Field::Nothing))
    }

    /// `isinstance(value, str)`: `Ok(Some)` for a string, `Ok(None)` for anything else, and `Err`
    /// for a string this can't read.
    pub fn string(&self) -> Result<Option<String>, OpError> {
        if !self.text().starts_with('"') {
            return Ok(None);
        }
        serde_json::from_str(self.text())
            .map(Some)
            .map_err(|_| python_says("a string this can't read"))
    }

    /// A list's items. `None` for anything else.
    pub fn items(&self) -> Option<Vec<Stored>> {
        if !self.text().starts_with('[') {
            return None;
        }
        serde_json::from_str(self.text()).ok()
    }

    /// `(value or [])` of a list.
    pub fn items_or_none(&self) -> Result<Vec<Stored>, OpError> {
        if let Some(items) = self.items() {
            return Ok(items);
        }
        match self.truthy() {
            Some(false) => Ok(Vec::new()),
            _ => Err(python_says("a list that isn't one")),
        }
    }
}

/// Python would have to say what this is. Nothing was answered.
pub fn python_says(what: &str) -> OpError {
    OpError::NotOwned { why: what.into() }
}

/// A JSON object in its stored order, as a `dict` holds it: a repeated key keeps its first place
/// and its last value.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Object(pub Vec<(String, Stored)>);

struct ObjectVisitor;

impl<'de> Visitor<'de> for ObjectVisitor {
    type Value = Object;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("an object")
    }

    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Object, A::Error> {
        let mut object = Object::default();
        while let Some(key) = map.next_key::<String>()? {
            let value: Box<RawValue> = map.next_value()?;
            object.set(&key, Stored(value));
        }
        Ok(object)
    }

    fn visit_seq<A: de::SeqAccess<'de>>(self, _: A) -> Result<Object, A::Error> {
        Err(de::Error::custom("not an object"))
    }
}

impl<'de> Deserialize<'de> for Object {
    fn deserialize<D: Deserializer<'de>>(from: D) -> Result<Object, D::Error> {
        from.deserialize_map(ObjectVisitor)
    }
}

impl Serialize for Object {
    fn serialize<S: Serializer>(&self, to: S) -> Result<S::Ok, S::Error> {
        let mut map = to.serialize_map(Some(self.0.len()))?;
        for (key, value) in &self.0 {
            map.serialize_entry(key, value)?;
        }
        map.end()
    }
}

impl Object {
    /// `None` for text that isn't an object, or holds a key this can't read.
    pub fn parse(text: &str) -> Option<Object> {
        serde_json::from_str(text).ok()
    }

    /// `(body or {})`, or `Err` where Python raises at the `.get` after it, or can't be read here.
    pub fn or_empty(text: &str) -> Result<Object, OpError> {
        if let Some(object) = Object::parse(text) {
            return Ok(object);
        }
        match serde_json::from_str::<Field>(text) {
            Ok(Field::Nothing) => Ok(Object::default()),
            _ => Err(python_says(
                "a body that is true to Python and not an object",
            )),
        }
    }

    /// `body.get(...)` with no `or` in front: a body that isn't an object raises, however false.
    pub fn exactly(text: &str) -> Result<Object, OpError> {
        Object::parse(text).ok_or_else(|| python_says("a body that isn't an object"))
    }

    pub fn get(&self, key: &str) -> Option<&Stored> {
        self.0.iter().find(|(name, _)| name == key).map(|(_, v)| v)
    }

    /// `.get(key)`: an absent key is `null`.
    pub fn get_or_null(&self, key: &str) -> Stored {
        self.get(key).cloned().unwrap_or_else(Stored::null)
    }

    /// `d[key] = value`.
    pub fn set(&mut self, key: &str, value: Stored) {
        match self.0.iter_mut().find(|(name, _)| name == key) {
            Some((_, held)) => *held = value,
            None => self.0.push((key.to_owned(), value)),
        }
    }

    pub fn remove(&mut self, key: &str) {
        self.0.retain(|(name, _)| name != key);
    }

    /// `.get(key)` is this string.
    pub fn says(&self, key: &str, word: &str) -> Result<bool, OpError> {
        match self.get(key) {
            None => Ok(false),
            Some(value) => Ok(value.string()?.as_deref() == Some(word)),
        }
    }

    /// `bool(.get(key))`.
    pub fn is_truthy(&self, key: &str) -> Result<bool, OpError> {
        match self.get(key) {
            None => Ok(false),
            Some(value) => value
                .truthy()
                .ok_or_else(|| python_says("a value this can't read")),
        }
    }

    /// `.get(key)` where the only readable answers are a string and nothing.
    pub fn text(&self, key: &str) -> Result<Option<String>, OpError> {
        match self.get(key) {
            None => Ok(None),
            Some(value) if value.is_null() => Ok(None),
            Some(value) => match value.string()? {
                Some(text) => Ok(Some(text)),
                None => Err(python_says("a value that isn't text")),
            },
        }
    }
}

/// Counts by name, in the order given, which a sorted map wouldn't keep.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Counts(pub Vec<(String, u64)>);

impl Serialize for Counts {
    fn serialize<S: Serializer>(&self, to: S) -> Result<S::Ok, S::Error> {
        let mut map = to.serialize_map(Some(self.0.len()))?;
        for (key, value) in &self.0 {
            map.serialize_entry(key, value)?;
        }
        map.end()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_stored_value_goes_on_as_it_came() {
        let text = r#"{"z":1.10,"a":{"y":2,"b":[3]}}"#;
        let got = Stored::parse(text).unwrap();
        assert_eq!(serde_json::to_string(&got).unwrap(), text);
    }

    #[test]
    fn an_object_keeps_its_order_and_a_repeated_key_its_first_place_and_last_value() {
        let got = Object::parse(r#"{"z":1,"a":2,"z":3}"#).unwrap();
        assert_eq!(serde_json::to_string(&got).unwrap(), r#"{"z":3,"a":2}"#);
        assert!(Object::parse("[1]").is_none());
        assert!(Object::parse("null").is_none());
    }

    #[test]
    fn what_is_not_an_object_is_empty_only_where_python_s_or_makes_it_so() {
        assert_eq!(Object::or_empty("null").unwrap(), Object::default());
        assert_eq!(Object::or_empty("[]").unwrap(), Object::default());
        assert!(Object::or_empty("[1]").is_err());
        assert!(Object::exactly("[]").is_err());
    }

    #[test]
    fn a_lone_surrogate_is_carried_and_not_read() {
        let got = Object::parse(r#"{"a":"\ud800","b":"ok"}"#).unwrap();
        assert!(got.text("a").is_err());
        assert_eq!(got.text("b").unwrap().as_deref(), Some("ok"));
        assert_eq!(got.get("a").unwrap().text(), r#""\ud800""#);
    }
}
