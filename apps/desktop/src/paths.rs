// SPDX-License-Identifier: Apache-2.0
use std::path::PathBuf;

pub fn get_data_dir() -> PathBuf {
    #[cfg(windows)]
    {
        if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
            return PathBuf::from(local_app_data).join("Praelector");
        }
    }
    #[cfg(unix)]
    {
        if let Ok(xdg_data) = std::env::var("XDG_DATA_HOME") {
            return PathBuf::from(xdg_data).join("praelector");
        }
        if let Ok(home) = std::env::var("HOME") {
            return PathBuf::from(home)
                .join(".local")
                .join("share")
                .join("praelector");
        }
    }
    std::env::temp_dir().join("Praelector")
}

pub fn get_log_dir() -> PathBuf {
    get_data_dir().join("logs")
}
