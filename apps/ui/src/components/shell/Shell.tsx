// SPDX-License-Identifier: Apache-2.0
import { Outlet } from "react-router";

import { Sidebar } from "./Sidebar";

export function Shell() {
  return (
    <div className="grid min-h-screen grid-cols-[16rem_minmax(0,1fr)] bg-paper text-ink dark:bg-night dark:text-dawn">
      <Sidebar />
      <main className="px-10 py-8">
        <Outlet />
      </main>
    </div>
  );
}
