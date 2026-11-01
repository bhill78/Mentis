//! Nothing to serve yet. P1.2 replaces this with the front.

fn main() -> std::process::ExitCode {
    eprintln!("mentis-server: this build has the shared interfaces only, and serves nothing");
    std::process::ExitCode::from(mentis_server::launch::EXIT_REFUSED as u8)
}

#[cfg(test)]
mod tests {
    #[test]
    fn this_build_owns_no_route() {
        assert!(mentis_server::HANDLERS.is_empty());
    }
}
