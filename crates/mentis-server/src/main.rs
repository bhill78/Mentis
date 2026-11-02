//! The front's binary. What it is started with is `contracts/launcher.md`, step 4.

use std::process::ExitCode;

use mentis_server::front::{self, Config};
use mentis_server::launch::{EXIT_REFUSED, SECRET_ENV};

fn refused(why: &str) -> ExitCode {
    eprintln!("mentis-server: {why}");
    ExitCode::from(EXIT_REFUSED as u8)
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let config = match Config::from_args(&args, std::env::var(SECRET_ENV).ok()) {
        Ok(config) => config,
        Err(why) => return refused(&why),
    };
    let runtime = match tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
    {
        Ok(runtime) => runtime,
        Err(error) => return refused(&format!("cannot start: {error}")),
    };
    let running = match runtime.block_on(front::start(config)) {
        Ok(running) => running,
        Err(front::Refused(why)) => return refused(&why),
    };
    runtime.block_on(running.serve());
    // Calls past the drain limit, and the blocking thread looking at the table, end with this.
    std::process::exit(0);
}

#[cfg(test)]
mod tests {
    #[test]
    fn this_build_answers_static_files() {
        assert!(mentis_server::HANDLERS.contains(&"static"));
    }
}
