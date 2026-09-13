// SPDX-License-Identifier: Apache-2.0
use std::collections::VecDeque;
use std::sync::{Arc, Mutex};

#[derive(Clone)]
pub struct RollingLogBuffer {
    capacity: usize,
    buffer: Arc<Mutex<VecDeque<String>>>,
}

impl RollingLogBuffer {
    pub fn new(capacity: usize) -> Self {
        Self {
            capacity,
            buffer: Arc::new(Mutex::new(VecDeque::with_capacity(capacity))),
        }
    }

    pub fn push(&self, line: String) {
        if let Ok(mut buf) = self.buffer.lock() {
            if buf.len() >= self.capacity {
                buf.pop_front();
            }
            buf.push_back(line);
        }
    }

    pub fn lines(&self) -> Vec<String> {
        if let Ok(buf) = self.buffer.lock() {
            buf.iter().cloned().collect()
        } else {
            Vec::new()
        }
    }
}
