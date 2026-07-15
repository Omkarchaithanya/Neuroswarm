//! Rust OKF SDK stub — HTTP client against /okf/*.

pub struct OkfClient {
    pub base_url: String,
}

impl OkfClient {
    pub fn new(base_url: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into(),
        }
    }
}
