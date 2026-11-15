// Cloudflare Pages Function: POST /api/vote
// Salva (o cancella, se vote = 0) il voto su una notizia nel KV "VOTES".
export async function onRequestPost({ request, env }) {
  let b;
  try {
    b = await request.json();
  } catch {
    return new Response("JSON non valido", { status: 400 });
  }
  const okId = typeof b.id === "string" && /^[a-f0-9]{10}$/.test(b.id);
  const okDate = typeof b.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(b.date);
  if (!okId || !okDate || ![-1, 0, 1].includes(b.vote)) {
    return new Response("Dati non validi", { status: 400 });
  }
  const key = `v:${b.date}:${b.id}`;
  if (b.vote === 0) {
    await env.VOTES.delete(key);
  } else {
    const cut = (s) => String(s ?? "").slice(0, 300);
    const record = {
      id: b.id,
      date: b.date,
      vote: b.vote,
      kind: cut(b.kind),
      title: cut(b.title),
      source: cut(b.source),
      category: cut(b.category),
      tags: Array.isArray(b.tags) ? b.tags.slice(0, 8).map(cut) : [],
      ts: Date.now(),
    };
    await env.VOTES.put(key, JSON.stringify(record));
  }
  return Response.json({ ok: true });
}
