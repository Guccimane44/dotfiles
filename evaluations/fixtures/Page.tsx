"use client";
import { useEffect, useState } from "react";
type Word = { id: string; label: string };
export async function loadPractice() {
  const words = await fetch("/api/words").then(r => r.json());
  const preferences = await fetch("/api/preferences").then(r => r.json());
  return { words, preferences };
}
export default function Practice({ words }: { words: Word[] }) {
  const [query, setQuery] = useState("");
  const [filtered, setFiltered] = useState(words);
  useEffect(() => { setFiltered(words.filter(w => w.label.includes(query))); }, [words, query]);
  const sorted = words.sort((a, b) => a.label.localeCompare(b.label));
  return <main><label>Filter<input value={query} onChange={e => setQuery(e.target.value)} /></label>
    <p>{sorted.length} total</p><ul>{filtered.map(w => <li key={w.id}>{w.label}</li>)}</ul></main>;
}
