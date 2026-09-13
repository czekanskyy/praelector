// SPDX-License-Identifier: Apache-2.0
#[cfg(windows)]
pub mod win {
    use std::mem::size_of;
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    pub struct JobObject {
        handle: HANDLE,
    }

    impl JobObject {
        pub fn create() -> Result<Self, String> {
            unsafe {
                let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if handle.is_null() {
                    return Err("Failed to create Windows Job Object".into());
                }

                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

                let res = SetInformationJobObject(
                    handle,
                    JobObjectExtendedLimitInformation,
                    &info as *const _ as *const _,
                    size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                );

                if res == 0 {
                    CloseHandle(handle);
                    return Err("Failed to set Job Object kill-on-close policy".into());
                }

                Ok(Self { handle })
            }
        }

        /// Assign a process to the Job Object.
        ///
        /// # Safety
        /// The caller must ensure that `process_handle` is a valid Windows process handle.
        pub unsafe fn assign_process(&self, process_handle: HANDLE) -> Result<(), String> {
            let res = AssignProcessToJobObject(self.handle, process_handle);
            if res == 0 {
                Err("Failed to assign process to Job Object".into())
            } else {
                Ok(())
            }
        }
    }

    impl Drop for JobObject {
        fn drop(&mut self) {
            unsafe {
                if !self.handle.is_null() {
                    CloseHandle(self.handle);
                }
            }
        }
    }
}
