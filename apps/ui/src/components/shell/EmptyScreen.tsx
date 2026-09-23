// SPDX-License-Identifier: Apache-2.0

export function EmptyScreen({ title, body }: { title: string; body: string }) {
  return (
    <section className="max-w-xl">
      <h1 className="font-serif text-3xl tracking-tight text-ink dark:text-dawn">{title}</h1>
      <p className="mt-3 text-base text-ink-soft dark:text-dawn-soft">{body}</p>
    </section>
  );
}
