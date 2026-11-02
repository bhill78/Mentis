//! `_turn_line`, `worker.py:751`: a Turn's readable content, references included. Public, because
//! `resolve` isn't its only reader: `find`'s Turn hits read it too.

use mentis_rules::Reading;

use crate::OpError;
use crate::stored::{Object, Stored, python_says};

/// `str(value)` of what an f-string is handed, as far as it is plainly the same here.
fn shown(value: Option<&Stored>) -> Result<String, OpError> {
    let Some(value) = value else {
        return Ok("None".to_owned());
    };
    if value.is_null() {
        return Ok("None".to_owned());
    }
    if let Some(text) = value.string()? {
        return Ok(text);
    }
    if value.is_true() {
        return Ok("True".to_owned());
    }
    if value.text() == "false" {
        return Ok("False".to_owned());
    }
    let digits = value.text().strip_prefix('-').unwrap_or(value.text());
    if !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit()) {
        return Ok(value.text().to_owned());
    }
    Err(python_says("a reference field that isn't plain text"))
}

/// `p.get('text') or ''`.
fn words_or_nothing(part: &Object) -> Result<String, OpError> {
    match part.get("text") {
        None => Ok(String::new()),
        Some(text) => match text
            .field()
            .ok_or_else(|| python_says("words this can't read"))?
        {
            mentis_rules::body::Field::Nothing => Ok(String::new()),
            mentis_rules::body::Field::Text(words) => Ok(words),
            mentis_rules::body::Field::NotText => Err(python_says("words that aren't text")),
        },
    }
}

/// A body's `parts`, each an object: what every read of a Turn walks.
pub fn parts_of(body: &Object) -> Result<Vec<Object>, OpError> {
    let Some(parts) = body.get("parts") else {
        return Ok(Vec::new());
    };
    parts
        .items_or_none()?
        .iter()
        .map(|part| Object::exactly(part.text()))
        .collect()
}

/// The line of one Turn, from how it now reads. `Err` wherever Python raises, or its text can't be
/// read here.
pub fn turn_line(reading: &Reading) -> Result<String, OpError> {
    if reading.deleted.is_some() {
        return Ok("[deleted]".to_owned());
    }
    let body = Object::exactly(&reading.body_json)?;
    let mut out = String::new();
    for part in parts_of(&body)? {
        let kind = part.get("type");
        let is_text = part.says("type", "text")?;
        if is_text {
            // `p.get("text", "")`, and `join` raises on anything else.
            match part.get("text") {
                None => {}
                Some(words) => match words.string()? {
                    Some(words) => out.push_str(&words),
                    None => return Err(python_says("a text part whose text isn't text")),
                },
            }
        } else if part.says("type", "object")? && part.is_truthy("ref")? {
            out.push_str(&words_or_nothing(&part)?);
            out.push_str(&format!(
                "[object:{}#{} {}]",
                shown(part.get("ref"))?,
                shown(part.get("key"))?,
                shown(part.get("exact"))?
            ));
        } else if part.is_truthy("ref")? {
            out.push_str(&words_or_nothing(&part)?);
            out.push_str(&format!("[{}:{}]", shown(kind)?, shown(part.get("ref"))?));
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use mentis_record::Id;

    fn read(body: &str) -> Reading {
        Reading {
            root: Id("ent-a".into()),
            body_json: body.into(),
            revision: None,
            deleted: None,
            python_says: false,
        }
    }

    #[test]
    fn a_line_is_its_words_and_its_references() {
        let got = turn_line(&read(
            r#"{"parts": [{"type": "text", "text": "see "},
                {"type": "entry", "ref": "ent-1", "text": "this"},
                {"type": "object", "ref": "ent-2", "key": "k", "exact": "e"},
                {"type": "file", "ref": "adm-3"},
                {"type": "other"}]}"#,
        ));
        assert_eq!(
            got.unwrap(),
            "see this[entry:ent-1][object:ent-2#k e][file:adm-3]"
        );
    }

    #[test]
    fn what_python_raises_on_is_python_s_to_answer() {
        assert!(turn_line(&read(r#"{"parts": [1]}"#)).is_err());
        assert!(turn_line(&read(r#"{"parts": [{"type": "text", "text": 3}]}"#)).is_err());
        assert!(turn_line(&read("[1]")).is_err());
        assert_eq!(turn_line(&read(r#"{"parts": null}"#)).unwrap(), "");
    }
}
